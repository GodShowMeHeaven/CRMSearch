import os
from flask import Flask, request, jsonify
from openai import OpenAI
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    app.logger.info(f"Received request: {request.headers} | Body: {request.get_data(as_text=True)}")
    # Получаем данные из тела запроса Sensei
    data = request.get_json(silent=True)
    if not data:
        app.logger.error("Failed to parse JSON data")
        return jsonify({'error': 'Invalid or missing JSON data'}), 400

    # Извлекаем поля из тела запроса
    lead_id = data.get('lead_id', 'Unknown Lead')
    company_name = data.get('company_name', 'Unknown Company')
    inn = data.get('INN', 'Unknown INN')

    # Формируем промпт для OpenAI
    prompt = (
        f"Обработайте данные лида из Sensei: "
        f"Lead ID: {lead_id}, "
        f"Название компании: {company_name}, "
        f"ИНН компании: {inn}. "
        f"Дайте рекомендации по дальнейшим действиям."
    )

    # Отправляем запрос в OpenAI API
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a CRM assistant. Provide concise recommendations based on lead data."},
                {"role": "user", "content": prompt}
            ]
        )
        ai_response = response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"OpenAI API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

    # Формируем JSON-ответ
    sensei_response = {
        'lead_id': lead_id,
        'company_name': company_name,
        'INN': inn,
        'recommendation': ai_response,
        'processed_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }

    return jsonify(sensei_response), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')