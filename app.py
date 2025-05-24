# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random
import time
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import requests

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

        # Update monitor status
        monitor.status = status
        monitor.response_time = response_time
        monitor.last_checked = datetime.utcnow()
        
        # Add to history
        history = MonitorHistory(
            monitor_id=monitor.id,
            status=status,
            response_time=response_time,
            message=message
        )
        db.session.add(history)
        
        # Update uptime stats (simplified for demo)
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

# Routes
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    monitors = Monitor.query.filter_by(user_id=user.id).all()
    
    # Quick stats
    up_count = sum(1 for m in monitors if m.status == 'up')
    down_count = sum(1 for m in monitors if m.status == 'down')
    
    return render_template('home.html', 
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
    return render_template('login.html')

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
    return render_template('register.html')

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
        
        # Schedule the monitor
        schedule_monitor(monitor)
        
        # Do initial check
        check_monitor(monitor.id)
        
        flash('Monitor added successfully')
        return redirect(url_for('home'))
    
    return render_template('add_monitor.html')

@app.route('/monitor/<int:id>')
def view_monitor(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    monitor = Monitor.query.get_or_404(id)
    if monitor.user_id != session['user_id']:
        return redirect(url_for('home'))
    
    # Get recent history for chart
    history = MonitorHistory.query.filter_by(monitor_id=id)\
        .order_by(MonitorHistory.timestamp.desc())\
        .limit(30)\
        .all()
    
    # Prepare chart data
    labels = [h.timestamp.strftime('%m-%d %H:%M') for h in reversed(history)]
    data = [h.response_time for h in reversed(history)]
    
    return render_template('monitor.html',
                         monitor=monitor,
                         labels=labels,
                         data=data)

@app.route('/delete/<int:id>')
def delete_monitor(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    monitor = Monitor.query.get_or_404(id)
    if monitor.user_id != session['user_id']:
        return redirect(url_for('home'))
    
    # Remove from scheduler
    try:
        scheduler.remove_job(f'monitor_{id}')
    except:
        pass
    
    db.session.delete(monitor)
    db.session.commit()
    flash('Monitor deleted successfully')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host="0.0.0.0" , port = 5000 , debug=True)
