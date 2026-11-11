from django.http import JsonResponse
from django.shortcuts import render


def page_not_found(request, exception=None):
    if request.path.startswith('/api/'):
        return JsonResponse({'error': 'El recurso solicitado no existe.'}, status=404)
    return render(request, 'views/html/404.html', status=404)


class Friendly404Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404 and request.resolver_match is None:
            return page_not_found(request)
        return response
