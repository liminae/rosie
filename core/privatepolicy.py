from core import policy

def apply():
    policy.reset()

def biases():
    return {}

def setmember(*args,**kwargs):
    raise RuntimeError(
        "private policy unavailable"
    )
