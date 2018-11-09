import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pyfcm import FCMNotification
from datetime import datetime, timedelta
import RPi.GPIO as GPIO
from time import sleep

##########################################

# Variables constantes
GPIO_RELE_1 = 17
GPIO_RELE_2 = 27
GPIO_RELE_3 = 22
GPIO_RELE_4 = 23

GPIO.setmode(GPIO.BCM)

# Se inicia una lista con los numeros de los pines GPIO

pinList = [GPIO_RELE_1, GPIO_RELE_2, GPIO_RELE_3, GPIO_RELE_4]

# Se recorren los pines y se setea el modo de salida (OUT) y el estado en alto (high)

for i in pinList: 
    GPIO.setup(i, GPIO.OUT) 
    GPIO.output(i, GPIO.HIGH)

# tiempor para dormir las operaciones en el ciclo principal

SleepTimeL = 2

##########################################
# Funciones

# Activa el rele asignado a la lavadora para iniciar el servicio
def activarRele(reserva):
    print("activar rele")
    lavadora_ref = db.collection(u'Lavadoras').document(reserva.get(u'lavadora'))
    lavadora_doc = lavadora_ref.get()
    releActivar  = int(lavadora_doc.get(u'rele'))

    if releActivar == 1:
        print "Activado rele 1"
        GPIO.output(GPIO_RELE_1, GPIO.LOW)
    elif releActivar == 2:
        print "Activado rele 2"
        GPIO.output(GPIO_RELE_2, GPIO.LOW)
    elif releActivar == 3:
        print "Activado rele 3"
        GPIO.output(GPIO_RELE_3, GPIO.LOW)
    elif releActivar == 4:
        print "Activado rele 4"
        GPIO.output(GPIO_RELE_4, GPIO.LOW)

# Funcion encargada de enviar el mensaje de notificacion al usuario
def enviarNotificacion(titulo, mensaje, usuario):
    print("enviar notificacion")
    dispositivos_ref = db.collection(u'devices')
    docs = dispositivos_ref.where(u'userId', u'==', usuario).get()

    for doc in docs:
        # Se consulta el token del dispositivo a ser enviado
        registration_id = doc.get("token")

        # Se crea el mensaje
        message_title = titulo
        message_body = mensaje
        result = push_service.notify_single_device(registration_id=registration_id, message_title=message_title, message_body=message_body)

        print(result)

# Funcion encargada de cancelar la reserva
def cancelarReserva(reserva):
    print("cancelar reserva")
    data = {
        u'confirmado': u'C',
        u'estado': False,
        u'fecha_inicio': reserva.get('fecha_inicio'),
        u'hora_fin': reserva.get('hora_fin'),
        u'hora_inicio': reserva.get('hora_inicio'),
        u'lavadora': reserva.get('lavadora'),
        u'precio': reserva.get('precio'),
        u'usuario': reserva.get('usuario'),
        u'valor': reserva.get('valor')
    }
    db.collection(u'Reservas').document(reserva.id).set(data)

    enviarNotificacion(u'Servicio Cancelado', u'Su reserva ha sido cancelado debido a que esta no fue confirmada.', reserva.get('usuario'))

# Desactiva el rele asignado a la lavadora al finalizar el servicio
def desactivarRele(reserva):
    print("detener el rele")
    lavadora_ref = db.collection(u'Lavadoras').document(reserva.get(u'lavadora'))
    lavadora_doc = lavadora_ref.get()
    releActivar  = int(lavadora_doc.get(u'rele'))

    if releActivar == 1:
        print "Desactivado rele 1"
        GPIO.output(GPIO_RELE_1, GPIO.HIGH)
    elif releActivar == 2:
        print "Desactivado rele 2"
        GPIO.output(GPIO_RELE_2, GPIO.HIGH)
    elif releActivar == 3:
        print "Desactivado rele 3"
        GPIO.output(GPIO_RELE_3, GPIO.HIGH)
    elif releActivar == 4:
        print "Desactivado rele 4"
        GPIO.output(GPIO_RELE_4, GPIO.HIGH)

    data = {
        u'confirmado': u'T',
        u'estado': False,
        u'fecha_inicio': reserva.get('fecha_inicio'),
        u'hora_fin': reserva.get('hora_fin'),
        u'hora_inicio': reserva.get('hora_inicio'),
        u'lavadora': reserva.get('lavadora'),
        u'precio': reserva.get('precio'),
        u'usuario': reserva.get('usuario'),
        u'valor': reserva.get('valor')
    }
    db.collection(u'Reservas').document(reserva.id).set(data)

    usuario_ref = db.collection(u'Usuarios')
    userDocs = usuario_ref.where(u'uid', u'==', reserva.get(u'usuario')).get()

    for userDoc in userDocs:
        nuevo_saldo    = int(userDoc.get(u'saldo')) - int(reserva.get(u'valor'))
        saldo_anterior = userDoc.get(u'saldo')

        data = {
            u'administrador': userDoc.get('administrador'),
            u'email': userDoc.get('email'),
            u'industrial': userDoc.get('industrial'),
            u'nombre': userDoc.get('nombre'),
            u'saldo': nuevo_saldo,
            u'saldo_anterior': saldo_anterior,
            u'uid': userDoc.get('uid')
        }
        db.collection(u'Usuarios').document(userDoc.id).set(data)

        enviarNotificacion(u'Servicio Finalizado', u'El servicio a finalizado, se ha cobrado el valor ' + str(reserva.get(u'valor')) + ', saldo actual: '+str(nuevo_saldo), reserva.get('usuario'))
    
##########################################

cred = credentials.Certificate('firebase_credentials.json')

# Se inicializa la app con las credenciales
default_app = firebase_admin.initialize_app(cred, {'projectId': 'project_id'})

# Se crea la conexion a la base de datos
db = firestore.client()

# Se configura el servicio de notificaciones
push_service = FCMNotification(api_key="server_api_key")

try:
    while True:

        # Se consulta la fecha actual del sistema
        now = datetime.now()

        reservas_ref = db.collection(u'Reservas')
        resDocs = reservas_ref.where(u'estado', u'==', True).get()

        # Estados reserva:
        # P: Pendiente
        # C: Cancelado
        # A: Aceptado
        # T: Terminado

        for resDoc in resDocs:
            trosos_hora_inicio = resDoc.get('hora_inicio').split(':')
            trosos_hora_fin = resDoc.get('hora_fin').split(':')

            # Si la hora es igual a la hora final de la reserva, entonces se termina la reserva y se desactiva el rele
            if now.hour == int(trosos_hora_fin[0]) and resDoc.get('confirmado') == 'A':
                # Se detiene la ejecucion del rele y se procede a realizar el cobro del servicio consumido
                desactivarRele(resDoc)

            # Si la hora es igual al de la reserva y esta ya se encuentra aceptada se activa el rele
            elif now.hour == int(trosos_hora_inicio[0]) and resDoc.get('confirmado') == 'A':
                # Se activa el rele de la lavadora
                activarRele(resDoc)
                
            # Si la hora es igual al de la reserva y esta aun se encuentra pendiente entonces se cancela
            elif now.hour == int(trosos_hora_inicio[0]) and resDoc.get('confirmado') == 'P':
                # Se cancela la reserva
                cancelarReserva(resDoc)
                
            # Si la hora es igual a la hora de la reserva menos 1, entonces se envia el mensaje de notificacion
            elif now.hour == int(trosos_hora_inicio[0])-1 and resDoc.get('confirmado') == 'P':
                # Se envia mensaje de notificacion
                enviarNotificacion(u"Confirmacion de Reserva", u"Su reserva esta a punto de empezar, por favor confirme si desea tomarla.", resDoc.get(u"usuario"))        

            sleep(SleepTimeL);

        dt = datetime.now() + timedelta(hours=1)
        dt = dt.replace(minute=00)

        while datetime.now() < dt:
            sleep(1)

# Se termina el programa limpiamente cuando es con teclado
except KeyboardInterrupt:
  print "  Quit"

  # Se reinician las configuraciones de los GPIO
  GPIO.cleanup()
