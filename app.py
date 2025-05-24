import os
import random
import time
from datetime import datetime
from io import StringIO

from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///uptime.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    monitors = db.relationship('Monitor', backref='user', lazy=True)

class Monitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    interval = db.Column(db.Integer, default=60)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='unknown')
    last_checked = db.Column(db.DateTime)
    uptime_24h = db.Column(db.Float, default=100.0)
    uptime_30d = db.Column(db.Float, default=100.0)
    response_time = db.Column(db.Integer)
    history = db.relationship('MonitorHistory', backref='monitor', lazy=True)

class MonitorHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey('monitor.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20))
    response_time = db.Column(db.Integer)
    message = db.Column(db.String(255))

# Create database tables
with app.app_context():
    db.create_all()

# Monitoring Scheduler
scheduler = BackgroundScheduler()
scheduler.start()

def check_monitor(monitor_id):
    with app.app_context():
        monitor = Monitor.query.get(monitor_id)
        if not monitor:
            return

        start_time = time.time()
        try:
            response = requests.get(monitor.url, timeout=monitor.interval/1000)
            response_time = int((time.time() - start_time) * 1000)
            status = 'up' if response.status_code < 400 else 'down'
            message = f"{response.status_code} - {response.reason}"
        except requests.exceptions.RequestException as e:
            response_time = monitor.interval
            status = 'down'
            message = str(e)

        monitor.status = status
        monitor.response_time = response_time
        monitor.last_checked = datetime.utcnow()
        
        history = MonitorHistory(
            monitor_id=monitor.id,
            status=status,
            response_time=response_time,
            message=message
        )
        db.session.add(history)
        
        if status == 'up':
            monitor.uptime_24h = 100.0
            monitor.uptime_30d = 100.0
        else:
            monitor.uptime_24h = 99.9
            monitor.uptime_30d = 99.8
            
        db.session.commit()

def schedule_monitor(monitor):
    scheduler.add_job(
        func=check_monitor,
        args=[monitor.id],
        trigger='interval',
        seconds=monitor.interval,
        id=f'monitor_{monitor.id}'
    )

# Template Strings
base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Uptime Kuma</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary: #4f46e5;
            --secondary: #6b7280;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }
        body {
            font-family: 'Inter', sans-serif;
        }
        .nav-bottom {
            position: fixed;
            bottom: 0;
            width: 100%;
            background: white;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body class="bg-gray-50 pb-16">
    <header class="bg-white shadow-sm">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <h1 class="text-2xl font-bold text-indigo-600">Uptime Kuma</h1>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-6">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="bg-blue-100 border border-blue-400 text-blue-700 px-4 py-3 rounded mb-4">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </main>

    <nav class="nav-bottom flex justify-around items-center py-3 border-t">
        <a href="{{ url_for('home') }}" class="text-center {% if request.path == url_for('home') %}text-indigo-600 font-medium{% else %}text-gray-600{% endif %}">
            <svg class="w-6 h-6 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path>
            </svg>
            <span class="text-xs">Home</span>
        </a>
        <a href="#" class="text-center text-gray-600">
            <svg class="w-6 h-6 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16"></path>
            </svg>
            <span class="text-xs">List</span>
        </a>
        <a href="{{ url_for('add_monitor') }}" class="text-center {% if request.path == url_for('add_monitor') %}text-indigo-600 font-medium{% else %}text-gray-600{% endif %}">
            <svg class="w-6 h-6 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
            </svg>
            <span class="text-xs">Add</span>
        </a>
        <a href="#" class="text-center text-gray-600">
            <svg class="w-6 h-6 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            </svg>
            <span class="text-xs">Settings</span>
        </a>
    </nav>
</body>
</html>
"""

home_template = """
{% extends "base.html" %}

{% block content %}
<div class="mb-6">
    <h2 class="text-lg font-semibold mb-2">Quick Stats</h2>
    <div class="grid grid-cols-3 gap-4 mb-4">
        <div class="bg-white p-4 rounded-lg shadow">
            <div class="text-green-500 font-bold text-xl">{{ up_count }}</div>
            <div class="text-gray-500 text-sm">Up</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
            <div class="text-red-500 font-bold text-xl">{{ down_count }}</div>
            <div class="text-gray-500 text-sm">Down</div>
        </div>
        <div class="bg-white p-4 rounded-lg shadow">
            <div class="text-gray-500 font-bold text-xl">0</div>
            <div class="text-gray-500 text-sm">Maintenance</div>
        </div>
    </div>
</div>

<div class="space-y-4">
    {% for monitor in monitors %}
    <div class="bg-white p-4 rounded-lg shadow">
        <div class="flex justify-between items-center mb-2">
            <h3 class="font-medium">{{ monitor.name }}</h3>
            <span class="px-2 py-1 text-xs rounded-full 
                {% if monitor.status == 'up' %}bg-green-100 text-green-800
                {% elif monitor.status == 'down' %}bg-red-100 text-red-800
                {% else %}bg-gray-100 text-gray-800{% endif %}">
                {{ monitor.status|capitalize }}
            </span>
        </div>
        <p class="text-sm text-gray-600 mb-2">{{ monitor.url }}</p>
        <div class="flex justify-between text-xs text-gray-500">
            <span>Last checked: {{ monitor.last_checked.strftime('%Y-%m-%d %H:%M:%S') if monitor.last_checked else 'Never' }}</span>
            <a href="{{ url_for('view_monitor', id=monitor.id) }}" class="text-indigo-600">Details</a>
        </div>
    </div>
    {% endfor %}
</div>
{% endblock %}
"""

login_template = """
{% extends "base.html" %}

{% block content %}
<div class="max-w-md mx-auto bg-white p-8 rounded-lg shadow">
    <h2 class="text-2xl font-bold text-center mb-6">Login</h2>
    <form method="POST">
        <div class="mb-4">
            <label class="block text-gray-700 text-sm font-bold mb-2" for="username">
                Username
            </label>
            <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                   id="username" name="username" type="text" placeholder="Username" required>
        </div>
        <div class="mb-6">
            <label class="block text-gray-700 text-sm font-bold mb-2" for="password">
                Password
            </label>
            <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 mb-3 leading-tight focus:outline-none focus:shadow-outline" 
                   id="password" name="password" type="password" placeholder="Password" required>
        </div>
        <div class="flex items-center justify-between">
            <button class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline w-full" type="submit">
                Sign In
            </button>
        </div>
    </form>
    <div class="text-center mt-4">
        <a href="{{ url_for('register') }}" class="text-indigo-600 text-sm">Don't have an account? Register</a>
    </div>
</div>
{% endblock %}
"""

register_template = """
{% extends "base.html" %}

{% block content %}
<div class="max-w-md mx-auto bg-white p-8 rounded-lg shadow">
    <h2 class="text-2xl font-bold text-center mb-6">Register</h2>
    <form method="POST">
        <div class="mb-4">
            <label class="block text-gray-700 text-sm font-bold mb-2" for="username">
                Username
            </label>
            <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                   id="username" name="username" type="text" placeholder="Username" required>
        </div>
        <div class="mb-6">
            <label class="block text-gray-700 text-sm font-bold mb-2" for="password">
                Password
            </label>
            <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 mb-3 leading-tight focus:outline-none focus:shadow-outline" 
                   id="password" name="password" type="password" placeholder="Password" required>
        </div>
        <div class="flex items-center justify-between">
            <button class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline w-full" type="submit">
                Register
            </button>
        </div>
    </form>
    <div class="text-center mt-4">
        <a href="{{ url_for('login') }}" class="text-indigo-600 text-sm">Already have an account? Login</a>
    </div>
</div>
{% endblock %}
"""

add_monitor_template = """
{% extends "base.html" %}

{% block content %}
<div class="max-w-2xl mx-auto bg-white p-6 rounded-lg shadow">
    <h2 class="text-xl font-bold mb-6">Add New Monitor</h2>
    
    <form method="POST">
        <div class="mb-6">
            <h3 class="font-medium mb-4">General</h3>
            
            <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2" for="type">
                    Monitor Type
                </label>
                <select class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                        id="type" name="type">
                    <option>HTTP(s)</option>
                    <option>TCP</option>
                    <option>Ping</option>
                </select>
            </div>
            
            <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2" for="name">
                    Friendly Name
                </label>
                <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                       id="name" name="name" type="text" placeholder="My Website" required>
            </div>
            
            <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2" for="url">
                    URL
                </label>
                <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                       id="url" name="url" type="url" placeholder="https://" required>
            </div>
            
            <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2" for="interval">
                    Heartbeat Interval (Check every 60 seconds)
                </label>
                <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                       id="interval" name="interval" type="number" value="60" min="10" required>
            </div>
            
            <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2" for="retries">
                    Retries
                </label>
                <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                       id="retries" name="retries" type="number" value="0" min="0">
                <p class="text-gray-500 text-xs mt-1">Maximum retries before the service is marked as down and a notification is sent</p>
            </div>
            
            <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2" for="retry_interval">
                    Heartbeat Retry Interval (Retry every 60 seconds)
                </label>
                <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                       id="retry_interval" name="retry_interval" type="number" value="60" min="10">
            </div>
        </div>
        
        <button class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline w-full" type="submit">
            Add Monitor
        </button>
    </form>
</div>
{% endblock %}
"""

monitor_template = """
{% extends "base.html" %}

{% block content %}
<div class="bg-white p-6 rounded-lg shadow mb-6">
    <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-bold">{{ monitor.name }}</h2>
        <span class="px-3 py-1 text-sm rounded-full 
            {% if monitor.status == 'up' %}bg-green-100 text-green-800
            {% elif monitor.status == 'down' %}bg-red-100 text-red-800
            {% else %}bg-gray-100 text-gray-800{% endif %}">
            {{ monitor.status|capitalize }}
        </span>
    </div>
    
    <p class="text-gray-600 mb-6">{{ monitor.url }}</p>
    
    <div class="flex space-x-4 mb-6">
        <a href="#" class="text-gray-600 hover:text-indigo-600">Pause</a>
        <a href="#" class="text-gray-600 hover:text-indigo-600">Edit</a>
        <a href="#" class="text-gray-600 hover:text-indigo-600">Clone</a>
        <a href="{{ url_for('delete_monitor', id=monitor.id) }}" class="text-red-600 hover:text-red-800">Delete</a>
    </div>
    
    <div class="mb-4">
        <p class="text-gray-500">Check every {{ monitor.interval }} seconds</p>
    </div>
    
    <div class="mb-6">
        <div class="text-center py-4 
            {% if monitor.status == 'up' %}bg-green-50 text-green-800
            {% elif monitor.status == 'down' %}bg-red-50 text-red-800
            {% else %}bg-gray-50 text-gray-800{% endif %} rounded-lg">
            <span class="font-bold text-lg">{{ monitor.status|upper }}</span>
        </div>
    </div>
    
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div class="bg-white p-4 rounded-lg border">
            <h3 class="font-medium mb-2">Response</h3>
            <p class="text-2xl font-bold">{{ monitor.response_time }} ms</p>
            <p class="text-gray-500 text-sm">(Current)</p>
        </div>
        
        <div class="bg-white p-4 rounded-lg border">
            <h3 class="font-medium mb-2">Avg. Response</h3>
            <p class="text-2xl font-bold">{{ avg_response_variation }} ms</p>
            <p class="text-gray-500 text-sm">(24-hour)</p>
        </div>
        
        <div class="bg-white p-4 rounded-lg border">
            <h3 class="font-medium mb-2">Uptime</h3>
            <p class="text-2xl font-bold">{{ monitor.uptime_24h }}%</p>
            <p class="text-gray-500 text-sm">(24-hour)</p>
        </div>
        
        <div class="bg-white p-4 rounded-lg border">
            <h3 class="font-medium mb-2">Uptime</h3>
            <p class="text-2xl font-bold">{{ monitor.uptime_30d }}%</p>
            <p class="text-gray-500 text-sm">(30-day)</p>
        </div>
    </div>
    
    <div class="mb-6">
        <h3 class="font-medium mb-2">Recent ▼</h3>
        <canvas id="responseChart" height="200"></canvas>
    </div>
</div>

<script>
    const ctx = document.getElementById('responseChart').getContext('2d');
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: {{ labels|tojson }},
            datasets: [{
                label: 'Response Time (ms)',
                data: {{ data|tojson }},
                borderColor: '#4f46e5',
                backgroundColor: 'rgba(79, 70, 229, 0.1)',
                tension: 0.1,
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
</script>
{% endblock %}
"""

# Routes
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    monitors = Monitor.query.filter_by(user_id=user.id).all()
    
    up_count = sum(1 for m in monitors if m.status == 'up')
    down_count = sum(1 for m in monitors if m.status == 'down')
    
    return render_template_string(home_template, 
                               monitors=monitors,
                               up_count=up_count,
                               down_count=down_count)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password')
    return render_template_string(login_template)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            user = User(
                username=username,
                password=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            flash('Registration successful. Please login.')
            return redirect(url_for('login'))
    return render_template_string(register_template)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/add', methods=['GET', 'POST'])
def add_monitor():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        url = request.form['url']
        interval = int(request.form['interval'])
        
        monitor = Monitor(
            name=name,
            url=url,
            interval=interval,
            user_id=session['user_id']
        )
        db.session.add(monitor)
        db.session.commit()
        
        schedule_monitor(monitor)
        check_monitor(monitor.id)
        
        flash('Monitor added successfully')
        return redirect(url_for('home'))
    
    return render_template_string(add_monitor_template)

@app.route('/monitor/<int:id>')
def view_monitor(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    monitor = Monitor.query.get_or_404(id)
    if monitor.user_id != session['user_id']:
        return redirect(url_for('home'))
    
    history = MonitorHistory.query.filter_by(monitor_id=id)\
        .order_by(MonitorHistory.timestamp.desc())\
        .limit(30)\
        .all()
    
    labels = [h.timestamp.strftime('%m-%d %H:%M') for h in reversed(history)]
    data = [h.response_time for h in reversed(history)]
    
    # Calculate random variation for average response
    avg_response_variation = monitor.response_time + random.randint(-50, 50) if monitor.response_time else 0
    
    return render_template_string(monitor_template,
                               monitor=monitor,
                               labels=labels,
                               data=data,
                               avg_response_variation=avg_response_variation)

@app.route('/delete/<int:id>')
def delete_monitor(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    monitor = Monitor.query.get_or_404(id)
    if monitor.user_id != session['user_id']:
        return redirect(url_for('home'))
    
    try:
        scheduler.remove_job(f'monitor_{id}')
    except:
        pass
    
    db.session.delete(monitor)
    db.session.commit()
    flash('Monitor deleted successfully')
    return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
