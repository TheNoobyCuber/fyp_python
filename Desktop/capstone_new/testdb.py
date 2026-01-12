import random
import time

def send_otp():
    otp = str(random.randint(100000, 999999))
    print(otp)

send_otp()