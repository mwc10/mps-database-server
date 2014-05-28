import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import subprocess


@csrf_exempt
def webhook(request):
    data = json.loads(request.body)

    print('request.body')
    print(request.body)
    print('data')
    print(data)

    try:
        if "refs/heads/master" in data.ref:
            if "nszceta" in data.pusher.name:
                subprocess.call(["touch", "~/touch-reload-production"])
                return HttpResponse(status=200)
    except KeyError:
        pass
    return HttpResponse(status=405)


@csrf_exempt
def database(request):
    data = json.loads(request.body)
    try:
        if "upddi" in data.data:
            return HttpResponse(
                subprocess.check_output(
                    ["pg_dump", "-Fc", "mpsdb"]
                )
            )
    except KeyError:
        pass
    return HttpResponse(status=405)