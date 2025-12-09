from flask import Flask, render_template

# Initialize the Flask application
app = Flask(__name__)

# 1. Home Page Route
@app.route('/')
def index():
    # Render the index.html template
    return render_template('index.html')

# Run the app
if __name__ == '__main__':
    # Run the app in debug mode
    app.run(debug=True)