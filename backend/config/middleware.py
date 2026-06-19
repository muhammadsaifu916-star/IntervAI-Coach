class CSRFExemptApiMiddleware:
    """Exempt API endpoints from CSRF protection since they use JWT tokens."""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Mark CSRF as done for all /api/ endpoints
        # They use JWT tokens, not CSRF tokens
        if request.path.startswith('/api/'):
            request.csrf_processing_done = True
        
        return self.get_response(request)
