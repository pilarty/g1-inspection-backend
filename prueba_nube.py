import getpass, requests
from pycognito import Cognito

u = Cognito("us-east-1_s9afR6W9w", "4044ectglilgk2u23qeit75pue", username=input("Usuario: "))
u.authenticate(password=getpass.getpass("Clave: "))
r = requests.get("https://lunkxzh9q5.execute-api.us-east-1.amazonaws.com/proyectos",
                 headers={"Authorization": "Bearer " + u.id_token}, timeout=20)
print(r.status_code, r.text)
