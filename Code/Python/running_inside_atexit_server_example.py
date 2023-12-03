from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/receive', methods=['POST'])
def receive_info():
    try:
        data = request.get_json()
        print("Received System Information:")
        print(json.dumps(data, indent=2))
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8080)
