import requests

receiver = "+000000000000000"
text = "SMS Test"
resp = requests.post('https://textbelt.com/text',{
                        'phone' : receiver,
                        'message' : text ,
                        'key' : 'textbelt'
                })

print(resp.json())
