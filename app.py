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

    # Формируем расширенный промпт для OpenAI с инструкцией по "поиску"
    prompt = (
        f"Найди и обработай данные о компании:\n"
        f"Название: {company_name}\n"
        f"ИНН: {inn}\n\n"
        f"Требуется собрать сведения из открытых источников (ФНС, Росстат, rusprofile.ru, СПАРК-Интерфакс или иные публичные базы):\n"
        f"- Среднесписочная численность сотрудников (ССЧ)\n"
        f"- Выручка (оборот) за 2024–2025 годы\n\n"
        f"Если точных данных нет, приведи наиболее свежую доступную информацию, оценки по аналогичным компаниям и укажи ссылки на источники.\n\n"
        f"Затем сделай краткие рекомендации по работе с этим клиентом на основе полученных данных "
        f"(например: маленькая компания, средняя, крупная; перспективность для продаж)."
    )


    # Отправляем запрос в OpenAI API
    try:
        response = client.responses.create(
            model="gpt-4o-mini",  # или "gpt-4o" для более точных результатов
            input=[
                {
                    "role": "system",
                    "content": "Ты — CRM-ассистент, который умеет использовать поиск по открытым источникам "
                            "для сбора бизнес-данных. Отвечай кратко, но указывай ссылки на источники."
                },
                {"role": "user", "content": prompt}
            ],
            tools=[{"type": "web_search_preview"}],  # включаем поиск
            max_output_tokens=800
        )
        ai_response = response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"OpenAI API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

    # Формируем JSON-ответ (GPT сама предоставит данные в ответе)
    sensei_response = {
        'lead_id': lead_id,
        'company_name': company_name,
        'INN': inn,
        'gpt_analysis': ai_response,  # Полный анализ от GPT (включая "найденные" данные и рекомендации)
        'processed_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }

    return jsonify(sensei_response), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')