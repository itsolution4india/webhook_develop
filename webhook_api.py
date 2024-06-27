from fastapi import FastAPI, Request, Response
import json
import os
import axios

app = FastAPI()

token = os.environ.get("TOKEN")
mytoken = os.environ.get("MYTOKEN")  # prasath_token

@app.get("/webhook")
async def verify_webhook(req: Request):
    mode = req.query_params.get("hub.mode")
    challenge = req.query_params.get("hub.challenge")
    verify_token = req.query_params.get("hub.verify_token")

    if mode and verify_token:
        if mode == "subscribe" and verify_token == mytoken:
            return Response(status_code=200, content=challenge)
        else:
            return Response(status_code=403)

@app.post("/webhook")
async def handle_webhook(req: Request):
    body_param = await req.json()

    print(json.dumps(body_param, indent=2))

    if body_param.get("object"):
        print("inside body param")
        if body_param.get("entry") and body_param["entry"][0].get("changes") and body_param["entry"][0]["changes"][0].get("value").get("messages") and body_param["entry"][0]["changes"][0].get("value").get("messages")[0]:
            phon_no_id = body_param["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
            from_ = body_param["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
            msg_body = body_param["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]

            print("phone number", phon_no_id)
            print("from", from_)
            print("body param", msg_body)

            async with axios.post(
                f"https://graph.facebook.com/v13.0/{phon_no_id}/messages?access_token={token}",
                json={
                    "messaging_product": "whatsapp",
                    "to": from_,
                    "text": {"body": f"Hi.. I'm Prasath, your message is {msg_body}"}
                },
                headers={"Content-Type": "application/json"}
            ) as response:
                print(response.status)

            return Response(status_code=200)
        else:
            return Response(status_code=404)

