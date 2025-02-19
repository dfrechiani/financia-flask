# app.py
import os
import json
import io
import requests
import pandas as pd
from flask import Flask, request, jsonify
from google.oauth2 import service_account
import gspread

app = Flask(__name__)

# ---------------------
# Configurações (via variáveis de ambiente)
# ---------------------
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "wpp-token-123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
# As credenciais do Google serão passadas como JSON string
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

# ---------------------
# Funções para acesso ao Google Sheets
# ---------------------
def get_gsheets_client():
    """Retorna um cliente gspread autenticado com as credenciais do service account."""
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client

def append_transaction_to_sheet(data_dict):
    """
    Adiciona uma transação na planilha.
    Ajuste as colunas conforme sua estrutura (ex.: Data, Categoria, Valor, Descrição).
    """
    try:
        client = get_gsheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID)
        wks = sheet.sheet1
        row = [
            data_dict.get("data", ""),
            data_dict.get("categoria", ""),
            data_dict.get("valor", ""),
            data_dict.get("descricao", "")
        ]
        wks.append_row(row)
        return True
    except Exception as e:
        print(f"Erro ao salvar no Google Sheets: {e}")
        return False

def get_transactions_csv():
    """
    Recupera todas as transações da planilha e gera um CSV (como string).
    """
    try:
        client = get_gsheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID)
        wks = sheet.sheet1
        records = wks.get_all_records()
        if not records:
            return None
        df = pd.DataFrame(records)
        csv_string = df.to_csv(index=False)
        return csv_string
    except Exception as e:
        print(f"Erro ao recuperar transações: {e}")
        return None

# ---------------------
# Funções para envio de mídia via WhatsApp Cloud API
# ---------------------
def upload_media(file_bytes, filename, mime_type):
    """
    Faz o upload do arquivo para a API do WhatsApp e retorna o media_id.
    """
    try:
        upload_url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/media"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}"
        }
        files = {
            "file": (filename, file_bytes, mime_type)
        }
        data = {
            "messaging_product": "whatsapp",
            "type": "document"
        }
        response = requests.post(upload_url, headers=headers, files=files, data=data)
        print("Upload media response:", response.status_code, response.text)
        if response.status_code == 200:
            res_json = response.json()
            return res_json.get("id")  # Retorna o media_id
        else:
            return None
    except Exception as e:
        print("Erro no upload de media:", e)
        return None

def send_document_message(phone_number, media_id, filename):
    """
    Envia uma mensagem do tipo “document” (arquivo) para o número especificado.
    """
    try:
        send_url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": filename
            }
        }
        response = requests.post(send_url, headers=headers, json=payload)
        print("Send document message response:", response.status_code, response.text)
        return response.status_code == 200
    except Exception as e:
        print("Erro ao enviar mensagem de documento:", e)
        return False

def send_whatsapp_text(phone_number, message):
    """
    Envia uma mensagem de texto simples para o número.
    """
    try:
        send_url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": message}
        }
        response = requests.post(send_url, headers=headers, json=payload)
        print("Send text message response:", response.status_code, response.text)
        return response.status_code == 200
    except Exception as e:
        print("Erro ao enviar mensagem de texto:", e)
        return False

# ---------------------
# Rotas do Webhook
# ---------------------
@app.route("/webhook", methods=["GET"])
def verify():
    """
    Verifica o webhook (usado pelo Meta para validação).
    """
    try:
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Erro de verificação", 403
    except Exception as e:
        return str(e), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Processa as mensagens recebidas do WhatsApp.
    Se o usuário enviar "relatório", gera e envia o CSV.
    Se for outra mensagem, registra um gasto simples (exemplo).
    """
    try:
        data = request.json
        print("Recebi dados:", data)
        if "messages" in data and data["messages"]:
            msg = data["messages"][0]
            phone_number = msg["from"]
            if msg["type"] == "text":
                text = msg["text"]["body"].strip().lower()
                if text == "relatorio":
                    # O usuário solicitou o relatório.
                    csv_string = get_transactions_csv()
                    if csv_string:
                        file_bytes = csv_string.encode("utf-8")
                        filename = "relatorio.csv"
                        mime_type = "text/csv"
                        media_id = upload_media(file_bytes, filename, mime_type)
                        if media_id:
                            if send_document_message(phone_number, media_id, filename):
                                return jsonify({"status": "success"}), 200
                            else:
                                send_whatsapp_text(phone_number, "Erro ao enviar relatório.")
                        else:
                            send_whatsapp_text(phone_number, "Erro ao gerar relatório.")
                    else:
                        send_whatsapp_text(phone_number, "Nenhuma transação encontrada para gerar relatório.")
                else:
                    # Exemplo: se a mensagem não for "relatório", registra um gasto simples.
                    # (Aqui você pode implementar sua lógica de processamento e categorização)
                    gasto = {
                        "data": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "categoria": "alimentacao",
                        "valor": "50",
                        "descricao": msg["text"]["body"]
                    }
                    append_transaction_to_sheet(gasto)
                    send_whatsapp_text(phone_number, "Gasto registrado com sucesso!")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("Erro no webhook:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # Para execução local, a porta padrão será 8080.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
