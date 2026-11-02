"""TP4 Simulación – Vacunatorio. Servidor web (Flask): muestra la pantalla y le pasa los parámetros al motor."""
import os
from flask import Flask, jsonify, render_template, request

from simulacion import Simulacion, periodo_del_generador

# index.html está en la misma carpeta que este archivo
app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/simular', methods=['POST'])
def simular():
    try:
        parametros = {nombre: float(valor) for nombre, valor in request.get_json().items()}
        parametros['maxIt'] = min(100000, max(1, int(parametros['maxIt'])))   # tope de 100000 iteraciones
        parametros['i'] = min(int(parametros['i']), parametros['maxIt'])
    except (TypeError, ValueError, AttributeError, KeyError):
        return jsonify(error='Parámetros inválidos'), 400

    resultado = Simulacion(parametros).ejecutar()
    resultado['periodo'] = periodo_del_generador(int(parametros['seed']), int(parametros['a']),
                                                 int(parametros['c']), int(parametros['m']))
    return jsonify(resultado)


if __name__ == '__main__':
    app.run(debug=True)
