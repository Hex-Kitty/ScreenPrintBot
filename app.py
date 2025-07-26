# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/quote', methods=['POST'])
def handle_question():
    data = request.get_json()
    user_message = data.get('message', '').lower().strip()
    
    bot_response = ""

    # --- The Bot's Brain ---
    if 'minimum' in user_message:
        bot_response = "Our minimum for a new screen print order is 24 pieces."
        
    elif 'turnaround' in user_message or 'how long' in user_message or 'turn around' in user_message:
        bot_response = "Standard turnaround is 7-10 business days after you approve the artwork."
        
    elif 'artwork' in user_message or 'file' in user_message:
        bot_response = "We prefer vector files like AI, PDF, or EPS for the best quality! You can learn more at https://examples.com/artwork-specs"
        
    # --- YOUR NEW 4th QUESTION ADDED HERE ---
    elif 'dtf' in user_message:
        bot_response = "We do offer DTF transfers! You can find more info at https://sportswearexpress.com/products/dtf-transfers"
    # ----------------------------------------
        
    # --- The Catch-All (Default Response) ---
    else:
        bot_response = "You better quit playin'! I'm a simple demo bot! Please ask about our minimums, turnaround, artwork files, or DTF."
        
    return jsonify(bot_response=bot_response)

if __name__ == '__main__':
    app.run(debug=True, port=5000)