import os
import re
from flask import Flask, request, jsonify
from openai import OpenAI
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import requests

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Инициализация клиента OpenAI
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

def clean_string(value: str) -> str:
    """Удаляем невидимые символы и пробелы по краям."""
    if not isinstance(value, str):
        return value
    # убираем пробелы, non-breaking space, thin space и др.
    return re.sub(r'[\u2009\u00A0\u200B]', '', value).strip()

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    app.logger.info(f"Received request: {request.headers} | Body: {request.get_data(as_text=True)}")

    # Получаем JSON (force=True подстрахует, если Content-Type некорректный)
    try:
        data = request.get_json(force=True, silent=False)
    except Exception as e:
        raw_body = request.get_data(as_text=True)
        app.logger.error(f"JSON parse error: {e} | Raw body: {raw_body}")
        return jsonify({'error': 'Invalid or missing JSON data'}), 400

    if not data:
        app.logger.error("No JSON data in request")
        return jsonify({'error': 'Invalid or missing JSON data'}), 400

    # Извлекаем данные и чистим от скрытых символов
    lead_id = clean_string(data.get('lead_id', 'Unknown Lead'))
    company_name = clean_string(data.get('company_name', ''))

    if not company_name:
        app.logger.error("Missing company_name in request")
        return jsonify({'error': 'Missing company_name'}), 400

    # Формируем промпт
    prompt = (
        f"Найди и обработай данные о компании:\n"
        f"Название: {company_name}\n\n"
        f"Ищи информацию строго только на следующих сайтах:\n"
        f"- Зачестный бизнес (https://zachestnyibiznes.ru/)\n"
        f"- ФНС (https://egrul.nalog.ru/index.html)\n"
        f"- Rusprofile (https://www.rusprofile.ru/)\n\n"
        f"Алгоритм действий:\n"
        f"1. Найди в указанных источниках топ-5 компаний, совпадающих по названию '{company_name}', зарегистрированных в Москве.\n"
        f"2. Для каждой компании собери:\n"
        f"   - Среднесписочную численность сотрудников (если нет данных — ставь прочерк)\n"
        f"   - Выручку (оборот) за последний доступный год (если нет данных — ставь прочерк)\n"
        f"   - Укажи год (период), за который собрана информация\n"
        f"3. Приведи по 5 ссылок, которые могут относиться к этим компаниям.\n\n"
        f"Строго соблюдай формат ответа для каждой компании:\n\n"
        f"Название юридического лица: ...\n"
        f"Среднесписочная численность: ...\n"
        f"Оборот за год: ...\n"
        f"Год: ...\n\n"
        f"Ссылки, которые могут относиться к компании:\n"
        f"- ...\n"
        f"- ...\n"
        f"- ...\n"
        f"- ...\n"
        f"- ...\n\n"
    )

    # Запрос к OpenAI
    try:
        response = client.responses.create(
            model="gpt-4o-mini",  # можно заменить на "gpt-4o"
            input=[
                {
                    "role": "system",
                    "content": "Ты — CRM-ассистент, который умеет использовать поиск по открытым источникам "
                               "для сбора бизнес-данных. Отвечай кратко, но обязательно указывай ссылки на источники."
                },
                {"role": "user", "content": prompt}
            ],
            tools=[{"type": "web_search_preview"}],
            tool_choice="auto",
            max_output_tokens=800
        )
        ai_response = response.output_text.strip()
    except Exception as e:
        app.logger.error(f"OpenAI API error: {str(e)}")
        return jsonify({'error': 'OpenAI API error'}), 502

    # Извлекаем хэш из заголовка
    hash_value = request.headers.get("X-Hash")
    if not hash_value:
        app.logger.error("Missing X-Hash header")
        return jsonify({'error': 'Missing X-Hash header'}), 400

    # Отправляем результат обратно в Sensei
    sensei_url = f"https://api.sensei.plus/webhook?hash={hash_value}&result={ai_response}"
    try:
        r = requests.get(sensei_url, headers={"User-Agent": "sensei-API-client/1.4"})
        app.logger.info(f"Sent result to Sensei: {r.status_code} | {r.text}")
    except Exception as e:
        app.logger.error(f"Failed to send result to Sensei: {str(e)}")
        return jsonify({'error': 'Failed to send result to Sensei'}), 500

    # Flask всегда должен вернуть 200 OK
    return jsonify({
        'status': 'success',
        'lead_id': lead_id,
        'company_name': company_name,
        'processed_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')
