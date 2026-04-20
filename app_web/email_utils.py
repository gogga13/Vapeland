from django.conf import settings
from django.core.mail import send_mail


def send_reset_code(email, code):
    subject = 'VapeLand: код скидання пароля'
    message = (
        'Вітаємо!\n\n'
        f'Ваш 6-значний код для скидання пароля: {code}\n'
        'Код дійсний 10 хвилин.\n\n'
        'Якщо ви не запитували скидання пароля, просто проігноруйте цей лист.'
    )
    return send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
