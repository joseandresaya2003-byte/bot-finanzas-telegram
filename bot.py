import os
import json
import io
import csv
import requests
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, request
from google import genai
from google.genai import types
from database import (
    init_db, guardar_gasto, obtener_resumen_mes, 
    guardar_recordatorio, obtener_recordatorios,
    borrar_ultimo_gasto, reiniciar_gastos_mes, 
    completar_recordatorio_por_titulo, borrar_recordatorio_por_titulo
)

app = Flask(__name__)

TELEGRAM_TOKEN = "8694080594:AAGvO2xjCRLqrC-PnSz3PzBesaCI_Ojkz-0"
URL_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/"
RENDER_URL = os.environ.get("RENDER_URL", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def enviar_mensaje(chat_id, texto):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    try:
        requests.post(URL_API + "sendMessage", json=payload)
    except Exception as e:
        print("Error al enviar mensaje:", e)

def descargar_foto_telegram(file_id):
    res = requests.get(f"{URL_API}getFile?file_id={file_id}").json()
    file_path = res["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    img_data = requests.get(download_url).content
    return Image.open(io.BytesIO(img_data))

def procesar_con_gemini(texto_usuario, total_actual, resumen_gastos, lista_recordatorios, imagen_pil=None):
    if not ai_client:
        return {"tipo": "chat", "respuesta": "⚠️ La API Key de Gemini no está configurada en las variables de entorno."}
    
    prompt = f"""
    Eres el asistente personal inteligente, cálido, súper organizado y detallista del usuario. Analiza el mensaje y/o la imagen y clasifícalo en una de estas categorías devolviendo UNICAMENTE un objeto JSON estricto:

    1. "gasto": Si el usuario registra un gasto en texto o foto (factura/recibo). Extrae: monto (número), categoria ("Comida", "Transporte", "Vehículo", "Servicios", "General"), descripcion (detalle).
    2. "recordatorio": Si pide guardar una tarea o pendiente. Extrae: titulo_recordatorio, fecha_hora.
    3. "completar_recordatorio": Si confirma que ya pagó/hizo algo (ej: "ya pagué la luz", "sí, ya lo hice"). Extrae: palabra_clave_completar.
    4. "borrar_ultimo_gasto": Si pide eliminar el último gasto.
    5. "reiniciar_gastos": Si pide reiniciar o borrar todos los gastos del mes.
    6. "borrar_recordatorio": Si pide eliminar un recordatorio por completo. Extrae: palabra_clave_borrar.
    7. "consultar_finanzas": Si el usuario pregunta por sus gastos o resumen del mes. 
        - IMPORTANTE: Redacta en la propiedad 'respuesta' un mensaje MUY BONITO, elegante, ordenado con emojis, detallando el total (${total_actual:,.0f}) y un desglose amigable de los movimientos.
    8. "consultar_recordatorios": Si el usuario pregunta qué pendientes tiene o qué falta por hacer. 
        - IMPORTANTE: Redacta en la propiedad 'respuesta' un mensaje MUY BONITO, motivador y ordenado con emojis listando cada tarea pendiente y su fecha/hora basada en: {lista_recordatorios}. Si está vacía, felicítalo con alegría.
    9. "chat": Conversación general, saludos, preguntas o consejos de ahorro. Redacta la 'respuesta'.

    Contexto actual:
    - Total gastado mes: ${total_actual:,.0f}
    - Gastos recientes: {resumen_gastos}
    - Recordatorios activos pendientes: {lista_recordatorios}

    Mensaje del usuario: "{texto_usuario if texto_usuario else 'Analiza la imagen adjunta'}"

    Estructura JSON requerida:
    {{
      "tipo": "gasto" | "recordatorio" | "completar_recordatorio" | "borrar_ultimo_gasto" | "reiniciar_gastos" | "borrar_recordatorio" | "consultar_finanzas" | "consultar_recordatorios" | "chat",
      "monto": 0.0,
      "categoria": "",
      "descripcion": "",
      "titulo_recordatorio": "",
      "fecha_hora": "",
      "palabra_clave_completar": "",
      "palabra_clave_borrar": "",
      "respuesta": ""
    }}
    """
    
    contents = [prompt]
    if imagen_pil:
        contents.append(imagen_pil)

    try:
        response = ai_client.models.generate_content(
            model='gemini-3.8-flash',
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print("ERROR REAL EN GEMINI:", str(e))
        return {"tipo": "chat", "respuesta": f"⚠️ Error técnico de Gemini: {str(e)}"}

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    try:
        datos = request.get_json()
        
        if "message" in datos:
            message = datos["message"]
            chat_id = message.get("chat", {}).get("id")
            texto = message.get("text", "").strip()
            photo = message.get("photo")
            caption = message.get("caption", "").strip()
            
            if chat_id:
                if texto == "/start":
                    enviar_mensaje(
                        chat_id,
                        "¡Hola! Soy tu asistente personal inteligente 🤖🧠💰.\n\n"
                        "Háblame con total naturalidad:\n"
                        "• *Gastos:* 'Gasté 30 mil en cena' o mándame foto de un recibo 📸\n"
                        "• *Recordatorios:* 'Recuérdame pagar el internet el viernes a las 3pm'\n"
                        "• *Confirmar tareas:* 'Ya pagué el internet' (para tacharlo)\n"
                        "• *Consultas:* '¿Qué tengo pendiente?' o '¿Cuánto llevo gastado?'\n"
                        "• *Gestión:* 'Borra el último gasto' o 'Reinicia los gastos del mes'"
                    )
                    return "OK", 200

                imagen_pil = None
                texto_a_evaluar = texto
                
                if photo:
                    file_id = photo[-1]["file_id"]
                    imagen_pil = descargar_foto_telegram(file_id)
                    texto_a_evaluar = caption if caption else "Analiza esta foto de recibo o gasto"

                rows_gastos, total_gastos = obtener_resumen_mes()
                recordatorios_activos = obtener_recordatorios(chat_id)
                
                resultado = procesar_con_gemini(
                    texto_a_evaluar, total_gastos, rows_gastos, recordatorios_activos, imagen_pil
                )
                tipo = resultado.get("tipo")
                
                if tipo == "gasto":
                    monto = resultado.get("monto", 0)
                    cat = resultado.get("categoria", "General")
                    desc = resultado.get("descripcion", "Gasto registrado")
                    if monto > 0:
                        guardar_gasto(monto, cat, desc)
                        origen = " 📸 (capturado de foto)" if imagen_pil else ""
                        enviar_mensaje(chat_id, f"✨ *¡Gasto registrado con éxito!{origen}*\n\n💰 *Monto:* ${monto:,.0f}\n📂 *Categoría:* {cat}\n📝 *Detalle:* {desc}\n\n_¡Sigue así manteniendo tus finanzas al día!_ 🚀")
                    else:
                        enviar_mensaje(chat_id, "Hmm, no logré detectar un monto claro. ¿Podrías indicármelo de nuevo?")

                elif tipo == "recordatorio":
                    titulo = resultado.get("titulo_recordatorio", "Tarea")
                    fhora = resultado.get("fecha_hora", "Próximamente")
                    guardar_recordatorio(chat_id, titulo, fhora)
                    enviar_mensaje(chat_id, f"📌 *¡Nuevo recordatorio agendado!*\n\n🎯 *Tarea:* {titulo}\n📅 *Cuándo:* {fhora}\n\n_Te avisaré en cuanto sea el momento._ ⏰")

                elif tipo == "completar_recordatorio":
                    palabra = resultado.get("palabra_clave_completar", "")
                    if palabra and completar_recordatorio_por_titulo(chat_id, palabra):
                        enviar_mensaje(chat_id, f"🎉 *¡Excelente trabajo!*\n\nHe marcado como completado y retirado de tus pendientes todo lo relacionado con '*{palabra}*'. ¡Un pendiente menos en tu lista! 🌟")
                    else:
                        enviar_mensaje(chat_id, f"No encontré ningún pendiente activo exacto con la palabra '{palabra}', ¡pero me alegra mucho si ya lo tachaste de tu lista! ✨")

                elif tipo == "borrar_ultimo_gasto":
                    if borrar_ultimo_gasto():
                        enviar_mensaje(chat_id, "🗑️ *¡Listo!* He eliminado el último gasto que habías registrado.")
                    else:
                        enviar_mensaje(chat_id, "No encontré ningún gasto registrado recientemente para eliminar.")

                elif tipo == "reiniciar_gastos":
                    reiniciar_gastos_mes()
                    enviar_mensaje(chat_id, "🔄 *¡Borrón y cuenta nueva!*\n\nHe reiniciado todos tus gastos de este mes a cero. Empezamos de nuevo con tus finanzas. 💡")

                elif tipo == "borrar_recordatorio":
                    palabra = resultado.get("palabra_clave_borrar", "")
                    if palabra and borrar_recordatorio_por_titulo(chat_id, palabra):
                        enviar_mensaje(chat_id, f"🗑️ He eliminado por completo el recordatorio relacionado con '*{palabra}*'.")
                    else:
                        enviar_mensaje(chat_id, f"No encontré ningún recordatorio que coincida con '{palabra}'.")

                elif tipo in ["consultar_finanzas", "consultar_recordatorios", "chat"]:
                    respuesta_ia = resultado.get("respuesta", "¡Entendido!")
                    enviar_mensaje(chat_id, respuesta_ia)

        return "OK", 200
    except Exception as e:
        print("ERROR CRÍTICO EN WEBHOOK:", str(e))
        try:
            chat_id = datos.get("message", {}).get("chat", {}).get("id")
            if chat_id:
                enviar_mensaje(chat_id, f"⚠️ *Error interno en el servidor:* `{str(e)}`")
        except:
            pass
        return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "¡Asistente Multimodal Inteligente con Gemini activo y listo!", 200

def configurar_webhook():
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{TELEGRAM_TOKEN}"
        requests.get(f"{URL_API}setWebhook?url={webhook_url}")

if __name__ == "__main__":
    init_db()
    configurar_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
