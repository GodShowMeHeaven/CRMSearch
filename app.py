import os
from flask import Flask, request, jsonify
from openai import OpenAI
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import requests

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Инициализация клиента OpenAI
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    app.logger.info(f"Received request: {request.headers} | Body: {request.get_data(as_text=True)}")

    # Получаем JSON из тела запроса
    data = request.get_json(silent=True)
    if not data:
        app.logger.error("Failed to parse JSON data")
        return jsonify({'error': 'Invalid or missing JSON data'}), 400

    # Извлекаем данные
    lead_id = data.get('lead_id', 'Unknown Lead')
    company_name = data.get('company_name', 'Unknown Company')
    inn = data.get('INN', 'Unknown INN')

    # Формируем промпт
    prompt = (
        f"Найди и обработай данные о компании:\n"
        f"Название: {company_name}\n"
        f"ИНН: {inn}\n\n"
        f"Требуется собрать сведения из открытых источников (ФНС, Росстат, rusprofile.ru, СПАРК-Интерфакс):\n"
        f"- Среднесписочная численность сотрудников (ССЧ)\n"
        f"- Выручка (оборот) за 2024–2025 годы\n\n"
        f"Если точных данных нет, приведи наиболее свежую доступную информацию, оценки по аналогичным компаниям и укажи ссылки.\n\n"
        f"Затем сделай краткие рекомендации по работе с этим клиентом "
        f"(например: маленькая, средняя или крупная компания; перспективность для продаж)."
    )

    # Запрос к OpenAI
    try:
        response = client.responses.create(
            model="gpt-4o-mini",  # или "gpt-4o"
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

    # Flask всегда должен вернуть 200 OK (Sensei уже получил результат по API)
    return jsonify({
        'status': 'success',
        'lead_id': lead_id,
        'company_name': company_name,
        'INN': inn,
        'processed_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')
