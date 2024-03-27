import requests

def sami_ai(text):
    if text is None or text == "":
        error_message = "You must enter text. You have not entered text."
        return {"response": error_message}
    else:
        
        headers = {
                'Host': '01d73592-4d64-43f7-b664-ecd679686756-00-30a5f50srzeko.janeway.replit.dev',
                'Connection': 'keep-alive',
                'Accept': '*/*',
                'User-Agent': 'com.tappz.aichat/1.2.2 iPhone/16.3.1 hw/iPhone12_5',
                'Accept-Language': 'ar',
                'Content-Type': 'application/json;charset=UTF-8'
            }
        try:
            response = requests.get(f'http://104.236.72.47:8909/?msg={text}', headers=headers)
            result = response.json()["response"]
            sami = f"""
{result}

┏━━⚇
┃━┃ t.me/SaMi_ye
┗━━━━━━━━
                """
            return {"response": sami}
        except Exception as e:
                return {"response": f"An unexpected error occurred. Try again. It will be fixed"}

def Devils_GPT(text, key,model):
    if key is None or key == "":
        error_message = "You must provide a valid API key."
        return {"response": error_message}
    if model is None or model == "":
        error_message = "You must provide a valid API model."
        return {"response": error_message}
    if text is None or text == "":
        error_message = "You must enter text. You have not entered text."
        return {"response": error_message}
    else:
        
        headers = {
                'Host': '01d73592-4d64-43f7-b664-ecd679686756-00-30a5f50srzeko.janeway.replit.dev',
                'Connection': 'keep-alive',
                'Accept': '*/*',
                'User-Agent': 'com.tappz.aichat/1.2.2 iPhone/16.3.1 hw/iPhone12_5',
                'Accept-Language': 'ar',
                'Content-Type': 'application/json;charset=UTF-8'
            }
        try:
            response = requests.get(f'http://104.236.72.47:4556/devils_gpt?msg={text}&key={key}&model={model}', headers=headers)
            result = response.json()["response"]
            sami = f"""
{result}
                """
            return {"response": sami}
        except Exception as e:
                return {"response": f"An unexpected error occurred. Try again. It will be fixed"}


def Worm_GPT(text, key,model):
    if key is None or key == "":
        error_message = "You must provide a valid API key."
        return {"response": error_message}
    if model is None or model == "":
        error_message = "You must provide a valid API model."
        return {"response": error_message}
    if text is None or text == "":
        error_message = "You must enter text. You have not entered text."
        return {"response": error_message}
    else:
        
        headers = {
                'Host': '01d73592-4d64-43f7-b664-ecd679686756-00-30a5f50srzeko.janeway.replit.dev',
                'Connection': 'keep-alive',
                'Accept': '*/*',
                'User-Agent': 'com.tappz.aichat/1.2.2 iPhone/16.3.1 hw/iPhone12_5',
                'Accept-Language': 'ar',
                'Content-Type': 'application/json;charset=UTF-8'
            }
        try:
            response = requests.get(f'http://104.236.72.47:4556/worm_gpt?msg={text}&key={key}&model={model}', headers=headers)
            result = response.json()["response"]
            sami = f"""
{result}
                """
            return {"response": sami}
        except Exception as e:
                return {"response": f"An unexpected error occurred. Try again. It will be fixed"}
