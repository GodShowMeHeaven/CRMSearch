import os
from flask import Flask, request, jsonify
from openai import OpenAI
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Для корректной работы за прокси (Railway использует прокси)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Инициализация OpenAI клиента
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    # Получаем данные из вебхука
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid or missing JSON data'}), 400

    # Извлекаем данные (адаптируйте под структуру хука от Sensei)
    user_input = data.get('message', '')
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400

    # Формируем промпт
    prompt = f"Ответь на следующий вопрос: {user_input}"

    # Запрос к OpenAI API
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        ai_response = response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"OpenAI API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

    # Возвращаем ответ
    return jsonify({'response': ai_response}), 200

# Обработка ошибок 404
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Railway использует переменную PORT
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')