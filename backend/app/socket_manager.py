import socketio
from typing import Dict, Any

# Crear el servidor Socket.IO con CORS permitido para el frontend
sio = socketio.AsyncServer(
    cors_allowed_origins=[
        "*"      # Reemplazar con tu dominio en producción
    ],
    async_mode="asgi"
)

# Crear la aplicación ASGI para montar en FastAPI
socket_app = socketio.ASGIApp(sio)

@sio.event
async def connect(sid: str, environ: Dict[str, Any]):
    """
    Evento cuando un cliente se conecta
    """
    print(f"🔌 Cliente conectado: {sid}")
    await sio.emit("conexion_exitosa", {"message": "Conectado al servidor de eventos"}, room=sid)


@sio.event
async def disconnect(sid: str):
    """
    Evento cuando un cliente se desconecta
    """
    print(f"🔌 Cliente desconectado: {sid}")


@sio.event
async def join_empresa(sid: str, empresa_id: int):
    """
    Cliente se une a una sala específica para recibir eventos de su empresa
    """
    room_name = f"empresa_{empresa_id}"
    await sio.enter_room(sid, room_name)
    print(f"📌 Cliente {sid} se unió a sala: {room_name}")
    await sio.emit("joined", {"room": room_name}, room=sid)


@sio.event
async def leave_empresa(sid: str, empresa_id: int):
    """
    Cliente sale de una sala
    """
    room_name = f"empresa_{empresa_id}"
    await sio.leave_room(sid, room_name)
    print(f"📌 Cliente {sid} salió de sala: {room_name}")


# Función auxiliar para emitir evento de nueva venta
async def emitir_nueva_venta(venta_dict: Dict[str, Any], empresa_id: int):
    """
    Emite un evento 'nueva_venta' a todos los clientes conectados
    que estén en la sala de la empresa correspondiente
    """
    room_name = f"empresa_{empresa_id}"
    print(f"📢 Emitiendo nueva venta a sala: {room_name}")
    await sio.emit("nueva_venta", venta_dict, room=room_name)


# Función auxiliar para emitir evento de cita actualizada
async def emitir_cita_actualizada(cita_dict: Dict[str, Any], empresa_id: int):
    """
    Emite un evento 'cita_actualizada' a todos los clientes conectados
    que estén en la sala de la empresa correspondiente
    """
    room_name = f"empresa_{empresa_id}"
    print(f"📢 [LOG 1] Emitiendo cita actualizada a sala: {room_name}")
    print(f"📢 [LOG 2] Datos a emitir: {cita_dict}")
    try:
        await sio.emit("cita_actualizada", cita_dict, room=room_name)
        print(f"✅ [LOG 3] Evento emitido exitosamente a sala {room_name}")
    except Exception as e:
        print(f"❌ [LOG ERROR] Falló la emisión: {str(e)}")
        import traceback
        traceback.print_exc()