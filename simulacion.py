"""TP4 Simulación – Vacunatorio A.
Motor de la simulación. Este archivo NO sabe nada de web: recibe parámetros y devuelve el vector de estado.
Unidad de tiempo: minutos.

Supuestos del modelo (ver documento de la Parte A):
- Cada aplicación de COVID abre UNA caja y vacuna exactamente 5 personas por orden de llegada (un grupo puede quedar partido).
- Una aplicación de gripe vacuna a todos los que esperan al empezar; usa las dosis sobrantes y abre las cajas que falten.
- La caja de gripe se abre al empezar la aplicación y vence X hs después; al vencer se descartan las dosis sobrantes.
- Una persona queda vacunada al TERMINAR la aplicación de su lote.
- Espera de un grupo COVID = fin del lote de su último integrante - fin del lote de su primer integrante.
  El promedio se calcula sobre los grupos que quedaron partidos (espera > 0)."""
import math

INFINITO = math.inf   # significa "este evento no está programado"

# Constantes del enunciado que no están en rojo (no se parametrizan)
GRUPO_MIN = 1
DOSIS_CAJA_COVID = 5      # además, es el mínimo de pacientes para abrir una caja COVID
DOSIS_CAJA_GRIPE = 10


class GeneradorCongruencial:
    """Congruencial mixto: x(n+1) = (a * x(n) + c) mod m   y   RND = x / m  (queda en [0,1)).
    La semilla no se usa como RND: el primer número usado es x1 / m."""

    def __init__(self, semilla, a, c, m):
        self.x, self.a, self.c, self.m = semilla, a, c, m

    def siguiente(self):
        self.x = (self.a * self.x + self.c) % self.m
        return self.x / self.m


class Grupo:
    """Objeto temporal: un grupo de personas que llega para vacunarse (COVID o gripe)."""

    def __init__(self, numero, tamano, hora_llegada):
        self.numero = numero
        self.tamano = tamano
        self.hora_llegada = hora_llegada
        self.vacunados = 0                 # integrantes que ya recibieron la dosis
        self.en_lote = 0                   # integrantes que se están vacunando en la aplicación actual
        self.hora_primera_dosis = None     # cuándo recibió la dosis el primer integrante (solo COVID)
        self.estado = 'En cola'            # En cola / Siendo vacunado / Esperando resto
        self.columna = None                # columna que ocupa en el vector de estado (solo para mostrar)

    def pendientes(self):
        """Integrantes que todavía esperan vacuna (sin contar los que se están vacunando ahora)."""
        return self.tamano - self.vacunados - self.en_lote


class Simulacion:
    def __init__(self, p):
        # --- parámetros (vienen de la pantalla) ---
        self.tiempo_total = p['T'] * 60                      # horas -> minutos
        self.max_iteraciones = int(p['maxIt'])
        self.filas_a_mostrar = int(p['i'])
        self.mostrar_desde = p['j'] * 60                     # horas -> minutos
        self.media_llegada_covid = p['perC'] / p['cntC']     # "4 veces cada 15 min" -> media 3,75 min
        self.media_llegada_gripe = p['mF']
        self.grupo_max = int(p['gmax'])
        self.vencimiento_gripe = p['X'] * 60                 # horas -> minutos
        self.segundos_por_paciente = p['seg']
        self.generador = GeneradorCongruencial(int(p['seed']), int(p['a']), int(p['c']), int(p['m']))

        # --- estado del sistema ---
        self.reloj = 0.0
        self.numero_fila = 0
        self.proxima_llegada_covid = INFINITO
        self.proxima_llegada_gripe = INFINITO
        self.fin_atencion = INFINITO                         # cuándo termina la aplicación en curso
        self.cola_covid = []                                 # grupos COVID en el sistema (orden de llegada)
        self.cola_gripe = []                                 # grupos de gripe en el sistema
        self.dosis_gripe_abierta = 0                         # dosis sobrantes de la caja de gripe abierta
        self.vencimiento_caja = INFINITO                     # cuándo vencen esas dosis
        self.enfermero_estado = 'Libre'                      # Libre / Aplicando COVID / Aplicando GRIPE
        self.enfermero_tipo = ''
        self.pacientes_en_lote = 0
        self.proximo_turno = 'COVID'                         # alterna COVID <-> GRIPE

        # --- acumuladores (las claves las lee la pantalla) ---
        self.acumuladores = {
            'cajasC': 0,      # cajas COVID colocadas
            'gP': 0,          # grupos COVID partidos que ya se retiraron
            'sP': 0.0,        # suma de las esperas de esos grupos (min)
        }

        # --- para armar la tabla (no son parte del modelo) ---
        self.evento = ''
        self.rnd_usados = {}               # RND y valores generados en la fila actual
        self.filas = []                    # filas que se van a mostrar
        self.ya_empezo_a_mostrar = False
        self.columnas_covid = []           # "casilleros" de columnas para los grupos COVID
        self.columnas_gripe = []
        self.contador_covid = 0
        self.contador_gripe = 0

    # ================= variables aleatorias =================
    def tiempo_entre_llegadas(self, media, clave):
        """Exponencial negativa por transformada inversa: t = -media * ln(1 - RND)."""
        rnd = self.generador.siguiente()
        tiempo = -media * math.log(1 - rnd)
        self.rnd_usados[clave] = rnd
        self.rnd_usados[clave + 't'] = tiempo
        return tiempo

    def tamano_de_grupo(self, clave):
        """Uniforme discreta entre 1 y grupo_max: tamaño = 1 + parte entera de RND * cantidad de valores."""
        rnd = self.generador.siguiente()
        tamano = GRUPO_MIN + int(rnd * (self.grupo_max - GRUPO_MIN + 1))
        self.rnd_usados['s' + clave] = rnd
        self.rnd_usados['s' + clave + 'n'] = tamano
        return tamano

    # ================= consultas sobre las colas =================
    def pacientes_covid_pendientes(self):
        return sum(grupo.pendientes() for grupo in self.cola_covid)

    def pacientes_gripe_pendientes(self):
        return sum(grupo.pendientes() for grupo in self.cola_gripe)

    # ================= eventos =================
    def llegada_covid(self):
        self.evento = 'Llegada grupo COVID'
        self.contador_covid += 1
        tamano = self.tamano_de_grupo('C')
        grupo = Grupo(self.contador_covid, tamano, self.reloj)
        self._asignar_columna(self.columnas_covid, grupo)
        self.cola_covid.append(grupo)
        self.proxima_llegada_covid = self.reloj + self.tiempo_entre_llegadas(self.media_llegada_covid, 'C')

    def llegada_gripe(self):
        self.evento = 'Llegada grupo gripe'
        self.contador_gripe += 1
        tamano = self.tamano_de_grupo('F')
        grupo = Grupo(self.contador_gripe, tamano, self.reloj)
        self._asignar_columna(self.columnas_gripe, grupo)
        self.cola_gripe.append(grupo)
        self.proxima_llegada_gripe = self.reloj + self.tiempo_entre_llegadas(self.media_llegada_gripe, 'F')

    def vencimiento_de_caja(self):
        self.evento = 'Vencimiento caja gripe'
        self.dosis_gripe_abierta = 0                          # se descartan las dosis sobrantes
        self.vencimiento_caja = INFINITO

    def fin_de_atencion(self):
        self.evento = 'Fin atención ' + self.enfermero_tipo
        if self.enfermero_tipo == 'COVID':
            self._terminar_aplicacion_covid()
        else:
            self._terminar_aplicacion_gripe()
        self.enfermero_estado = 'Libre'
        self.enfermero_tipo = ''
        self.pacientes_en_lote = 0
        self.fin_atencion = INFINITO

    def _terminar_aplicacion_covid(self):
        acum = self.acumuladores
        for grupo in self.cola_covid:
            if grupo.en_lote == 0:
                continue                                    # este grupo no participó de la aplicación
            grupo.vacunados += grupo.en_lote
            grupo.en_lote = 0
            if grupo.hora_primera_dosis is None:
                grupo.hora_primera_dosis = self.reloj       # primera vez que algún integrante recibe la dosis
            if grupo.vacunados == grupo.tamano:             # el grupo ya se puede retirar
                espera = self.reloj - grupo.hora_primera_dosis
                if espera > 0:                              # quedó partido entre dos o más cajas
                    acum['gP'] += 1
                    acum['sP'] += espera
            else:
                grupo.estado = 'Esperando resto'
        for grupo in [g for g in self.cola_covid if g.vacunados == g.tamano]:
            self._liberar_columna(self.columnas_covid, grupo)
            self.cola_covid.remove(grupo)

    def _terminar_aplicacion_gripe(self):
        for grupo in [g for g in self.cola_gripe if g.en_lote > 0]:   # los que llegaron durante la aplicación siguen esperando
            self._liberar_columna(self.columnas_gripe, grupo)
            self.cola_gripe.remove(grupo)

    # ================= decisión del enfermero =================
    def asignar_enfermero(self):
        """Si el enfermero está libre, decide qué vacuna aplicar y arranca la aplicación."""
        if self.enfermero_estado != 'Libre':
            return
        tipo = self._elegir_tipo_de_vacuna()
        if tipo is None:
            return                                           # no hay nada para hacer, sigue libre
        if tipo == 'COVID':
            pacientes = self._aplicar_covid()
        else:
            pacientes = self._aplicar_gripe()
        self.enfermero_estado = 'Aplicando ' + tipo
        self.enfermero_tipo = tipo
        self.pacientes_en_lote = pacientes
        self.fin_atencion = self.reloj + pacientes * self.segundos_por_paciente / 60
        self.proximo_turno = 'GRIPE' if tipo == 'COVID' else 'COVID'   # el turno siguiente es el opuesto

    def _elegir_tipo_de_vacuna(self):
        hay_covid = self.pacientes_covid_pendientes() >= DOSIS_CAJA_COVID
        hay_gripe = self.pacientes_gripe_pendientes() > 0
        if self.proximo_turno == 'COVID':
            if hay_covid:
                return 'COVID'
            if hay_gripe:
                return 'GRIPE'        # le tocaba COVID pero no hay suficientes: sigue con gripe
            return None
        if hay_gripe:                 # le tocaba gripe
            return 'GRIPE'
        if hay_covid:
            return 'COVID'            # no hay nadie de gripe pero sí hay COVID: no queda ocioso
        return None

    def _aplicar_covid(self):
        """Abre UNA caja y reparte sus dosis entre los grupos, en orden de llegada."""
        self.acumuladores['cajasC'] += 1
        dosis_libres = DOSIS_CAJA_COVID
        for grupo in self.cola_covid:
            if dosis_libres == 0:
                break
            cantidad = min(grupo.pendientes(), dosis_libres)   # puede vacunar solo una parte del grupo
            grupo.en_lote = cantidad
            grupo.estado = 'Siendo vacunado'
            dosis_libres -= cantidad
        return DOSIS_CAJA_COVID - dosis_libres

    def _aplicar_gripe(self):
        """Vacuna a todos los que esperan; usa las dosis sobrantes y abre cajas nuevas si hace falta."""
        pacientes = self.pacientes_gripe_pendientes()
        for grupo in self.cola_gripe:
            grupo.en_lote = grupo.tamano
            grupo.estado = 'Siendo vacunado'
        if self.dosis_gripe_abierta >= pacientes:
            self.dosis_gripe_abierta -= pacientes
        else:
            faltan = pacientes - self.dosis_gripe_abierta
            cajas_nuevas = math.ceil(faltan / DOSIS_CAJA_GRIPE)
            self.dosis_gripe_abierta = cajas_nuevas * DOSIS_CAJA_GRIPE - faltan
            self.vencimiento_caja = self.reloj + self.vencimiento_gripe   # el vencimiento cuenta desde que se abre
        if self.dosis_gripe_abierta == 0:
            self.vencimiento_caja = INFINITO                  # no quedan dosis que puedan vencer
        return pacientes

    # ================= bucle principal =================
    def ejecutar(self):
        self.evento = 'Inicio'
        self.proxima_llegada_covid = self.tiempo_entre_llegadas(self.media_llegada_covid, 'C')
        self.proxima_llegada_gripe = self.tiempo_entre_llegadas(self.media_llegada_gripe, 'F')
        self._registrar_fila()
        while True:
            if self.numero_fila >= self.max_iteraciones:
                self.evento = 'Límite de iteraciones'
                break
            tiempo, que_evento = self._proximo_evento()
            if tiempo > self.tiempo_total:
                self.reloj = self.tiempo_total
                self.evento = 'Fin de simulación'
                break
            self.reloj = tiempo                               # el reloj salta al próximo evento
            if que_evento == 'FIN_ATENCION':
                self.fin_de_atencion()
            elif que_evento == 'VENCIMIENTO':
                self.vencimiento_de_caja()
            elif que_evento == 'LLEGADA_COVID':
                self.llegada_covid()
            else:
                self.llegada_gripe()
            self.asignar_enfermero()
            self._registrar_fila()
        return {'rows': self.filas, 'last': armar_fila(self, es_ultima=True), 'A': self.acumuladores,
                'n': self.numero_fila, 't': self.reloj}

    def _proximo_evento(self):
        """Devuelve (tiempo, evento) del evento más cercano. Si hay empate gana el primero de la lista."""
        eventos = [(self.fin_atencion, 'FIN_ATENCION'), (self.vencimiento_caja, 'VENCIMIENTO'),
                   (self.proxima_llegada_covid, 'LLEGADA_COVID'), (self.proxima_llegada_gripe, 'LLEGADA_GRIPE')]
        return min(eventos, key=lambda e: e[0])

    # ================= solo para mostrar la tabla =================
    def _registrar_fila(self):
        if not self.ya_empezo_a_mostrar and self.reloj >= self.mostrar_desde:
            self.ya_empezo_a_mostrar = True
        if self.ya_empezo_a_mostrar and len(self.filas) < self.filas_a_mostrar:
            self.filas.append(armar_fila(self))
        self.rnd_usados = {}
        self.numero_fila += 1

    @staticmethod
    def _asignar_columna(columnas, grupo):
        """Cada grupo ocupa un casillero de columnas mientras está en el sistema; al irse, otro lo reutiliza."""
        if None in columnas:
            grupo.columna = columnas.index(None)
        else:
            columnas.append(None)
            grupo.columna = len(columnas) - 1
        columnas[grupo.columna] = grupo

    @staticmethod
    def _liberar_columna(columnas, grupo):
        columnas[grupo.columna] = None


def armar_fila(sim, es_ultima=False):
    """Foto del sistema en este instante: una fila del vector de estado (en formato que lee la pantalla)."""
    def tiempo(valor):
        return None if valor == INFINITO else valor            # JSON no admite infinito

    grupos_covid = None if es_ultima else [
        g and [g.numero, g.tamano, g.vacunados, g.en_lote, g.estado, g.hora_llegada, g.hora_primera_dosis]
        for g in sim.columnas_covid]
    grupos_gripe = None if es_ultima else [
        g and [g.numero, g.tamano, g.estado, g.hora_llegada] for g in sim.columnas_gripe]
    return {
        'n': sim.numero_fila, 'ev': sim.evento, 't': sim.reloj, 'R': dict(sim.rnd_usados),
        'nc': sim.proxima_llegada_covid, 'nf': sim.proxima_llegada_gripe,
        'fin': tiempo(sim.fin_atencion), 'ven': tiempo(sim.vencimiento_caja),
        'st': sim.enfermero_estado, 'turn': sim.proximo_turno, 'lote': sim.pacientes_en_lote,
        'gC': len(sim.cola_covid), 'pC': sim.pacientes_covid_pendientes(),
        'gF': len(sim.cola_gripe), 'pF': sim.pacientes_gripe_pendientes(),
        'box': sim.dosis_gripe_abierta, 'A': dict(sim.acumuladores),
        'tc': grupos_covid, 'tf': grupos_gripe,
    }
