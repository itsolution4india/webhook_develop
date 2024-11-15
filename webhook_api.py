import os
import logging
from flask import Flask, jsonify, request
import json
from datetime import datetime
import mysql.connector
import requests
import time
from functools import lru_cache
import threading

app = Flask(__name__)

verify_token = "hello"
LOGS_DIR = 'message_logs'
DASHBOARD_URL = "https://wtsdealnow.com/user_responses/"

# Set up logging
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

logging.basicConfig(filename=os.path.join(LOGS_DIR, 'app.log'),
                    level=logging.DEBUG,  # Changed to DEBUG for more detailed logging
                    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

def handle_message(request):
    logging.info("Entering handle_message function")
    try:
        body = request.get_json()
        
        if not body:
            logging.warning("Received empty JSON payload.")
            return jsonify({"status": "ok"}), 200

        if 'entry' not in body or not body['entry']:
            logging.warning(f"Invalid webhook payload: {body}")
            return jsonify({"status": "ok"}), 200

        event_id = body['entry'][0].get('id')
        if not event_id:
            logging.warning(f"Missing event_id in payload: {body}")
            return jsonify({"status": "ok"}), 200

        data = parse_webhook_response(body)

        for entry in body['entry']:
            changes = entry['changes']
            for change in changes:
                value = change['value']
                statuses = value.get('statuses', [])
                messages = value.get('messages', [])
                for message in messages:
                    if message['type'] == 'text':
                        text_message = message['text'].get('body')
                        logging.info(f"Text message: {text_message}")
                    elif message['type'] == 'button':
                        button_message = message['button'].get('text')
                        logging.info(f"Button message: {button_message}")
                    elif message['type'] == 'interactive':
                        interactive_type = message['interactive'].get('type')
                        logging.info(f"Interactive type: {interactive_type}")
                        if interactive_type == 'button_reply':
                            interactive_btn_reply_msg = message['interactive']['button_reply'].get('title')
                            logging.info(f"Button reply message: {interactive_btn_reply_msg}")
                        elif interactive_type == 'list_reply':
                            interactive_list_reply_msg = message['interactive']['list_reply'].get('title')
                            logging.info(f"List reply message: {interactive_list_reply_msg}")

        store_webhook_data(data, body)

        filename = os.path.join(LOGS_DIR, f'{event_id}.log')
        with open(filename, 'a+') as file:
            file.write(json.dumps(data))
            file.write("\n")

        logging.info("-------------------------------------------------")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logging.exception(f"Error processing message: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def verify(request):
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logging.debug(f"Verification parameters - Mode: {mode}, Token: {token}, Challenge: {challenge}")

    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            return challenge, 200
        else:
            logging.warning("Webhook verification failed: Invalid token.")
            return "Verification token mismatch", 403
    else:
        logging.warning("Webhook verification failed: Missing parameters.")
        return "Bad request parameters", 400

def next_actions(response):
    logging.info("Entering next_actions function")
    main_response = response
    try:
        message_text = response['entry'][0]['changes'][0]['value']['messages'][0]['button']['text']
        logging.debug(f"Extracted message text: {message_text}")
    except:
        message_text = None
        logging.warning("Failed to extract message text from response")
    
    try:
        user_response = response['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        logging.debug(f"Extracted user text message: {message_text}")
    except:
        user_response = None   
        logging.warning("Failed to extract user message text from response")
    
    logging.info(f"message_text {message_text}")
    logging.info(f"response: {response}")
    if message_text or user_response:
        try:
            phone_number = response['entry'][0]['changes'][0]['value']['contacts'][0]['wa_id']
            response = requests.post(DASHBOARD_URL, json={'response': response})
            if response.status_code == 200:
                logging.info(f"Response successfully sent to the dashboard. {main_response}")
            else:
                logging.warning(f"Failed to send response to dashboard. Status code: {response.status_code}, Response: {response.json()}")
        except requests.RequestException as e:
            logging.error(f"Error sending response to dashboard: {e}")
    else:
        logging.info("No message text found, skipping dashboard update")

def parse_webhook_response(response):
    report = {}
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime('%Y-%m-%d %H:%M:%S')

    report['Date'] = formatted_datetime
    
    for entry in response['entry']:
        changes = entry['changes']
        for change in changes:
            value = change['value']
            metadata = value.get('metadata', {})
            report['display_phone_number'] = metadata.get('display_phone_number')
            report['phone_number_id'] = metadata.get('phone_number_id')
            
            message_template_id = value.get('message_template_id')
            message_template_name = value.get('message_template_name')

            if message_template_id and message_template_name:
                report['message_template_id'] = message_template_id
                report['message_template_name'] = message_template_name
                
            statuses = value.get('statuses', [])
            for status in statuses:
                report['waba_id'] = status.get('id')
                report['status'] = status.get('status')
                report['message_timestamp'] = status.get('timestamp')
                report['contact_wa_id'] = status.get('recipient_id')
                if 'errors' in status:
                    error_details = status['errors'][0]
                    report['error_code'] = error_details.get('code')
                    report['error_title'] = error_details.get('title')
                    report['error_message'] = error_details.get('message')
                    report['error_data'] = error_details.get('error_data', {}).get('details')

            contacts = value.get('contacts', [])
            for contact in contacts:
                report['contact_name'] = contact['profile'].get('name')
                report['contact_wa_id'] = contact.get('wa_id')

            messages = value.get('messages', [])
            for message in messages:
                report['message_from'] = message.get('from')
                report['status'] = 'reply'
                report['waba_id'] = message.get('id')
                report['message_timestamp'] = message.get('timestamp')
                report['message_type'] = message.get('type')
                
                if message['type'] == 'text':
                    report['message_body'] = message['text'].get('body')
                elif message['type'] == 'button':
                    report['message_body'] = message['button'].get('text')
                elif message['type'] == 'interactive':
                    interactive_type = message['interactive'].get('type')
                    if interactive_type == 'button_reply':
                        report['message_body'] = message['interactive']['button_reply'].get('title')
                        logging.info(f"button_reply, {message['interactive']['button_reply'].get('title')}")
                    elif interactive_type == 'list_reply':
                        report['message_body'] = message['interactive']['list_reply'].get('title')
                        logging.info(f"list_reply: {message['interactive']['list_reply'].get('title')}")
                    elif interactive_type == 'nfm_reply':
                        report['message_body'] = message['interactive']['nfm_reply'].get('response_json')
                        logging.info(f"trigger here: {message['interactive']['nfm_reply'].get('response_json')}")
                else:
                    report['message_body'] = ""
    
    return report

def store_webhook_data(report, body):
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="fedqrbtb_wtsdealnow",
            password="Solution@97",
            database="fedqrbtb_report",
            charset="utf8mb4"
        )

        cursor = connection.cursor()

        check_query = "SELECT COUNT(*) FROM webhook_responses WHERE message_timestamp = %s AND contact_wa_id = %s"
        cursor.execute(check_query, (report.get('message_timestamp'), report.get('contact_wa_id')))

        count = cursor.fetchone()[0]
        logging.debug(f"Found {count} existing entries")

        if count == 0:
            next_actions(body)
            add_response = (
                "INSERT INTO webhook_responses "
                "(Date, display_phone_number, phone_number_id, waba_id, contact_wa_id, status, message_timestamp, error_code, error_message, contact_name, message_from, message_type, message_body) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            )

            data_response = (
                report.get('Date'),
                report.get('display_phone_number'),
                report.get('phone_number_id'),
                report.get('waba_id'),
                report.get('contact_wa_id'),
                report.get('status'),
                report.get('message_timestamp'),
                report.get('error_code'),
                report.get('error_message'),
                report.get('contact_name'),
                report.get('message_from'),
                report.get('message_type'),
                report.get('message_body')
            )

            cursor.execute(add_response, data_response)
            connection.commit()
        else:
            update_query = (
                "UPDATE webhook_responses SET "
                "Date = %s, display_phone_number = %s, phone_number_id = %s, waba_id = %s, contact_wa_id = %s, "
                "status = %s, error_code = %s, error_message = %s, contact_name = %s, message_from = %s, "
                "message_type = %s, message_body = %s WHERE message_timestamp = %s AND contact_wa_id = %s"
            )

            update_data = (
                report.get('Date'),
                report.get('display_phone_number'),
                report.get('phone_number_id'),
                report.get('waba_id'),
                report.get('contact_wa_id'),
                report.get('status'),
                report.get('error_code'),
                report.get('error_message'),
                report.get('contact_name'),
                report.get('message_from'),
                report.get('message_type'),
                report.get('message_body'),
                report.get('message_timestamp'),
                report.get('contact_wa_id')
            )

            cursor.execute(update_query, update_data)
            connection.commit()
            logging.info("Webhook data updated successfully.")

    except mysql.connector.Error as err:
        logging.error(f"Database error: {err}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/", methods=["POST", "GET"])
def webhook():
    logging.info(f"Received {request.method} request at webhook endpoint")
    if request.method == "GET":
        logging.info(f"Got GET request: {request.args.get("hub.mode")} {datetime.now()}")
        return verify(request)
    elif request.method == "POST":
        logging.info(f"Got POST request: {request.get_json()} {datetime.now()}")
        return handle_message(request)


if __name__ == "__main__":
    logging.info("Starting Flask application")
    app.run()