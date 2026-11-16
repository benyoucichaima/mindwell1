def role_layout(request):
    u = request.user
    if u.is_authenticated:
        is_psy = getattr(u, "user_type", "") == "psychologue"
        return {
            "is_psy": is_psy,
            "dashboard_base": "layouts/dashboard_psy.html" if is_psy
                              else "layouts/dashboard_patient.html",
        }
    return {}