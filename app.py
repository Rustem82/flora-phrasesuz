from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import json
import re
import os
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'flora-phraseology-secret-key-2024')

# Используем PostgreSQL на Vercel, SQLite локально
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # Для Vercel (PostgreSQL)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Для локальной разработки (SQLite)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///phrases.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ITEMS_PER_PAGE'] = 20

# Создаём папку для загрузок (только локально)
if not os.environ.get('VERCEL'):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'


# ==================== МОДЕЛИ ====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Phrase(db.Model):
    __tablename__ = 'phrases'
    id = db.Column(db.Integer, primary_key=True)
    german = db.Column(db.String(200), nullable=False)
    uzbek = db.Column(db.String(200), nullable=False)
    literal = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    origin = db.Column(db.Text, nullable=True)
    example = db.Column(db.Text, nullable=True)
    plant_type = db.Column(db.String(50), nullable=True, default='растение')
    usage_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    neutral_meaning = db.Column(db.Text, nullable=True)


class TranslationLog(db.Model):
    __tablename__ = 'translation_logs'
    id = db.Column(db.Integer, primary_key=True)
    source_text = db.Column(db.Text, nullable=False)
    target_text = db.Column(db.Text, nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    matched_phrase_id = db.Column(db.Integer, db.ForeignKey('phrases.id'), nullable=True)
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50), nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== ФУНКЦИИ ====================

def normalize_string(s):
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r'[^\w\s]', '', s)
    return s


def find_best_match(german_input, direction='de2uz'):
    if not german_input.strip():
        return None, 0
    normalized_input = normalize_string(german_input)
    phrases = Phrase.query.all()
    best_match = None
    best_score = 0
    for phrase in phrases:
        search_text = phrase.german if direction == 'de2uz' else phrase.uzbek
        normalized_search = normalize_string(search_text)
        if normalized_search == normalized_input:
            return phrase, 100
        if normalized_search in normalized_input or normalized_input in normalized_search:
            score = 80
        else:
            input_words = normalized_input.split()
            search_words = normalized_search.split()
            common = sum(1 for w in input_words if any(w in sw or sw in w for sw in search_words))
            score = 40 + min(common, 3) * 10 if common > 0 else 0
        if score > best_score:
            best_score = score
            best_match = phrase
    return (best_match, best_score) if best_score >= 30 else (None, 0)


def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password_hash=generate_password_hash('admin123'))
            db.session.add(admin)
            db.session.commit()
            print("👑 Администратор создан: admin / admin123")
        if Phrase.query.count() == 0:
            initial_phrases = [
                {
                    "german": "Den Wald vor lauter Bäumen nicht sehen",
                    "uzbek": "Daraxtlar tufayli o'rmonni ko'rmaslik",
                    "literal": "Yog'ochlar sababli o'rmonni ko'rmaslik",
                    "description": "Mayda-chuyda tafsilotlarga haddan tashqari e'tibor qaratib, umumiy manzarani ko'ra olmaslik.",
                    "notes": "Ko'pincha tanqidiy vaziyatlarda ishlatiladi",
                    "origin": "Qadimgi yunon falsafasi (Lukian)",
                    "example": "U daraxtlar tufayli o'rmonni ko'rmaydi va loyihaning barbod bo'layotganini sezmaydi.",
                    "plant_type": "дерево",
                    "neutral_meaning": "Vor lauter Details das Wesentliche übersehen"
                },
                {
                    "german": "Durch die Blume sagen",
                    "uzbek": "Gul orqali aytmoq",
                    "literal": "Gul orqali aytmoq",
                    "description": "Biror narsani to'g'ridan-to'g'ri emas, balki qiya, ishora bilan aytmoq.",
                    "notes": "Nozik va muloyimlik bilan gapirish usuli.",
                    "origin": "O'rta asrlar Yevropasidagi gul tili (floriografiya) dan",
                    "example": "Er hat es ihr durch die Blume gesagt, dass er sie mag.",
                    "plant_type": "цветок",
                    "neutral_meaning": "Etwas indirekt, versteckt oder höflich andeuten"
                }
            ]
            for phrase_data in initial_phrases:
                phrase = Phrase(**phrase_data, usage_count=0, created_at=datetime.utcnow())
                db.session.add(phrase)
            db.session.commit()
            print(f"🌿 Добавлено {len(initial_phrases)} начальных фразеологизмов!")
        print(f"📚 Всего фраз в базе: {Phrase.query.count()}")
        print("✅ Инициализация завершена!")


# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dictionary')
def dictionary():
    return render_template('dictionary.html')


@app.route('/api/phrases')
def get_phrases():
    phrases = Phrase.query.order_by(Phrase.usage_count.desc()).all()
    return jsonify([{
        'id': p.id,
        'german': p.german,
        'uzbek': p.uzbek,
        'literal': p.literal,
        'description': p.description,
        'notes': p.notes,
        'origin': p.origin,
        'example': p.example,
        'plant_type': p.plant_type if p.plant_type else 'растение',
        'usage_count': p.usage_count,
        'neutral_meaning': p.neutral_meaning
    } for p in phrases])


@app.route('/admin/api/phrases/paginated')
@login_required
def get_phrases_paginated():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', app.config['ITEMS_PER_PAGE'], type=int)
        search = request.args.get('search', '', type=str)
        plant_type = request.args.get('plant_type', '', type=str)
        query = Phrase.query
        if search and search.strip():
            search_term = f"%{search}%"
            query = query.filter(db.or_(Phrase.german.ilike(search_term), Phrase.uzbek.ilike(search_term), Phrase.description.ilike(search_term)))
        if plant_type and plant_type != 'all' and plant_type.strip():
            query = query.filter_by(plant_type=plant_type)
        query = query.order_by(Phrase.usage_count.desc(), Phrase.id.desc())
        total = query.count()
        total_pages = math.ceil(total / per_page) if per_page > 0 else 1
        offset = (page - 1) * per_page
        phrases = query.offset(offset).limit(per_page).all()
        return jsonify({
            'success': True,
            'data': [{
                'id': p.id,
                'german': p.german,
                'uzbek': p.uzbek,
                'literal': p.literal or '',
                'description': p.description or '',
                'notes': p.notes or '',
                'origin': p.origin or '',
                'example': p.example or '',
                'plant_type': p.plant_type if p.plant_type else 'растение',
                'usage_count': p.usage_count,
                'neutral_meaning': p.neutral_meaning or ''
            } for p in phrases],
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_items': total,
                'total_pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages,
                'prev_page': page - 1 if page > 1 else None,
                'next_page': page + 1 if page < total_pages else None
            }
        })
    except Exception as e:
        print(f"Ошибка в пагинации: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': [], 'pagination': {'current_page': 1, 'per_page': per_page, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False, 'prev_page': None, 'next_page': None}}), 200


@app.route('/api/translate', methods=['POST'])
def translate():
    data = request.json
    source_text = data.get('text', '')
    direction = data.get('direction', 'de2uz')
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if not source_text.strip():
        return jsonify({'success': False, 'translation': '', 'note': '🌸 Введите фразеологизм о флоре...'})
    result = {'success': False, 'translation': '', 'note': '', 'matched': False}
    if direction == 'de2uz':
        phrase, score = find_best_match(source_text, 'de2uz')
        if phrase:
            phrase.usage_count += 1
            db.session.commit()
            result = {'success': True, 'translation': phrase.uzbek, 'note': f'🌿 "{phrase.german}"\n📖 {phrase.description}\n💡 {phrase.example}' if phrase.example else f'🌿 "{phrase.german}"\n📖 {phrase.description}', 'matched': True, 'phrase_id': phrase.id}
        else:
            result = {'success': False, 'translation': '🌱 Аналог не найден', 'note': 'К сожалению, этот фразеологизм о флоре пока отсутствует в нашем саду.'}
    else:
        phrase, score = find_best_match(source_text, 'uz2de')
        if phrase:
            phrase.usage_count += 1
            db.session.commit()
            result = {'success': True, 'translation': phrase.german, 'note': f'🌿 "{phrase.uzbek}"\n📖 {phrase.description}\n💡 {phrase.example}' if phrase.example else f'🌿 "{phrase.uzbek}"\n📖 {phrase.description}', 'matched': True, 'phrase_id': phrase.id}
        else:
            result = {'success': False, 'translation': '🌱 Аналог не найден', 'note': 'Этот узбекский фразеологизм о растениях ещё не добавлен.'}
    log = TranslationLog(source_text=source_text, target_text=result.get('translation', ''), direction=direction, matched_phrase_id=result.get('phrase_id'), success=result.get('success', False), ip_address=ip_address[:50] if ip_address else None)
    db.session.add(log)
    db.session.commit()
    return jsonify(result)


# ==================== JSON ЗАГРУЗКА И ЭКСПОРТ ====================

@app.route('/admin/api/export', methods=['GET'])
@login_required
def export_json():
    phrases = Phrase.query.all()
    data = [{'german': p.german, 'uzbek': p.uzbek, 'literal': p.literal, 'description': p.description, 'notes': p.notes, 'origin': p.origin, 'example': p.example, 'plant_type': p.plant_type, 'neutral_meaning': p.neutral_meaning} for p in phrases]
    return jsonify({'success': True, 'count': len(data), 'data': data})


@app.route('/admin/api/import', methods=['POST'])
@login_required
def import_json():
    try:
        data = request.json
        phrases_data = data.get('phrases', [])
        overwrite = data.get('overwrite', False)
        if not phrases_data:
            return jsonify({'success': False, 'error': 'Нет данных для импорта'}), 400
        if overwrite:
            Phrase.query.delete()
        count = 0
        for item in phrases_data:
            existing = Phrase.query.filter_by(german=item.get('german')).first()
            if not existing or overwrite:
                phrase = Phrase(german=item.get('german'), uzbek=item.get('uzbek'), literal=item.get('literal', ''), description=item.get('description', ''), notes=item.get('notes', ''), origin=item.get('origin', ''), example=item.get('example', ''), plant_type=item.get('plant_type', 'растение'), neutral_meaning=item.get('neutral_meaning', ''), usage_count=0, created_at=datetime.utcnow())
                db.session.add(phrase)
                count += 1
        db.session.commit()
        return jsonify({'success': True, 'count': count, 'message': f'Успешно импортировано {count} фразеологизмов'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/admin/api/upload', methods=['POST'])
@login_required
def upload_json_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
    if not file.filename.endswith('.json'):
        return jsonify({'success': False, 'error': 'Пожалуйста, загрузите JSON файл'}), 400
    overwrite = request.form.get('overwrite', 'false') == 'true'
    try:
        content = file.read().decode('utf-8')
        phrases_data = json.loads(content)
        if isinstance(phrases_data, list):
            pass
        elif isinstance(phrases_data, dict) and 'phrases' in phrases_data:
            phrases_data = phrases_data['phrases']
        else:
            return jsonify({'success': False, 'error': 'Неверный формат JSON. Ожидается массив объектов.'}), 400
        if overwrite:
            Phrase.query.delete()
        count = 0
        for item in phrases_data:
            phrase = Phrase(german=item.get('german'), uzbek=item.get('uzbek'), literal=item.get('literal', ''), description=item.get('description', ''), notes=item.get('notes', ''), origin=item.get('origin', ''), example=item.get('example', ''), plant_type=item.get('plant_type', 'растение'), neutral_meaning=item.get('neutral_meaning', ''), usage_count=0, created_at=datetime.utcnow())
            db.session.add(phrase)
            count += 1
        db.session.commit()
        return jsonify({'success': True, 'count': count, 'message': f'Успешно загружено {count} фразеологизмов из файла {file.filename}'})
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Ошибка парсинга JSON: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== АДМИН-ПАНЕЛЬ ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('🌿 Неверное имя пользователя или пароль')
    return render_template('admin/login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin_dashboard():
    total_phrases = Phrase.query.count()
    total_translations = TranslationLog.query.count()
    successful = TranslationLog.query.filter_by(success=True).count()
    success_rate = round((successful / total_translations * 100) if total_translations > 0 else 0)
    top_phrases = Phrase.query.order_by(Phrase.usage_count.desc()).limit(5).all()
    flower_count = Phrase.query.filter_by(plant_type='цветок').count()
    tree_count = Phrase.query.filter_by(plant_type='дерево').count()
    fruit_count = Phrase.query.filter_by(plant_type='фрукт').count()
    plant_count = Phrase.query.filter_by(plant_type='растение').count()
    grass_count = Phrase.query.filter_by(plant_type='трава').count()
    garden_count = Phrase.query.filter_by(plant_type='сад').count()
    poliz_count = Phrase.query.filter_by(plant_type='бахча').count()
    sabzavot_count = Phrase.query.filter_by(plant_type='овощ').count()
    bobovoe_count = Phrase.query.filter_by(plant_type='бобовое_растение').count()
    getreide_count = Phrase.query.filter_by(plant_type='getreide').count()
    stats = {
        'total_phrases': total_phrases,
        'total_translations': total_translations,
        'successful_matches': success_rate,
        'flower_count': flower_count,
        'tree_count': tree_count,
        'fruit_count': fruit_count,
        'plant_count': plant_count,
        'grass_count': grass_count,
        'garden_count': garden_count,
        'poliz_count': poliz_count,
        'sabzavot_count': sabzavot_count,
        'bobovoe_count': bobovoe_count,
        'getreide_count': getreide_count
    }
    return render_template('admin/dashboard.html', stats=stats, top_phrases=top_phrases, items_per_page=app.config['ITEMS_PER_PAGE'])


# ==================== ОБНОВЛЕННЫЕ АДМИН-МАРШРУТЫ ====================

@app.route('/admin/api/phrases', methods=['POST'])
@login_required
def admin_add_phrase():
    data = request.json
    try:
        phrase = Phrase(german=data['german'], uzbek=data['uzbek'], literal=data.get('literal', ''), description=data.get('description', ''), notes=data.get('notes', ''), origin=data.get('origin', ''), example=data.get('example', ''), plant_type=data.get('plant_type', 'растение'), neutral_meaning=data.get('neutral_meaning', ''))
        db.session.add(phrase)
        db.session.commit()
        return jsonify({'success': True, 'id': phrase.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/admin/api/phrases/<int:phrase_id>', methods=['PUT'])
@login_required
def admin_update_phrase(phrase_id):
    phrase = Phrase.query.get_or_404(phrase_id)
    data = request.json
    try:
        phrase.german = data.get('german', phrase.german)
        phrase.uzbek = data.get('uzbek', phrase.uzbek)
        phrase.literal = data.get('literal', phrase.literal)
        phrase.description = data.get('description', phrase.description)
        phrase.notes = data.get('notes', phrase.notes)
        phrase.origin = data.get('origin', phrase.origin)
        phrase.example = data.get('example', phrase.example)
        phrase.plant_type = data.get('plant_type', phrase.plant_type)
        phrase.neutral_meaning = data.get('neutral_meaning', phrase.neutral_meaning)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/admin/api/phrases/<int:phrase_id>', methods=['DELETE'])
@login_required
def admin_delete_phrase(phrase_id):
    phrase = Phrase.query.get_or_404(phrase_id)
    db.session.delete(phrase)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/phrases/paginated')
def get_phrases_paginated_public():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 24, type=int)
        search = request.args.get('search', '', type=str)
        plant_type = request.args.get('plant_type', '', type=str)
        query = Phrase.query
        if search and search.strip():
            search_term = f"%{search}%"
            query = query.filter(db.or_(Phrase.german.ilike(search_term), Phrase.uzbek.ilike(search_term), Phrase.description.ilike(search_term)))
        if plant_type and plant_type != 'all' and plant_type.strip():
            query = query.filter_by(plant_type=plant_type)
        query = query.order_by(Phrase.usage_count.desc(), Phrase.id.desc())
        total = query.count()
        total_pages = math.ceil(total / per_page) if per_page > 0 else 1
        offset = (page - 1) * per_page
        phrases = query.offset(offset).limit(per_page).all()
        return jsonify({
            'success': True,
            'data': [{
                'id': p.id,
                'german': p.german,
                'uzbek': p.uzbek,
                'literal': p.literal or '',
                'description': p.description or '',
                'notes': p.notes or '',
                'origin': p.origin or '',
                'example': p.example or '',
                'plant_type': p.plant_type if p.plant_type else 'растение',
                'usage_count': p.usage_count,
                'neutral_meaning': p.neutral_meaning or ''
            } for p in phrases],
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_items': total,
                'total_pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages,
                'prev_page': page - 1 if page > 1 else None,
                'next_page': page + 1 if page < total_pages else None
            }
        })
    except Exception as e:
        print(f"Ошибка в публичной пагинации: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': [], 'pagination': {'current_page': 1, 'per_page': per_page, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False, 'prev_page': None, 'next_page': None}}), 200


# ==================== ДЛЯ VERCEL ====================
# Инициализируем базу данных при запуске
# ==================== ДЛЯ VERCEL ====================
# Инициализируем базу данных при запуске
with app.app_context():
    try:
        db.create_all()

        # Удаляем старого админа если он с логином admin
        old_admin = User.query.filter_by(username='admin').first()
        if old_admin:
            db.session.delete(old_admin)
            db.session.commit()
            print("🗑️ Старый администратор 'admin' удалён")

        # Создаём нового админа
        if not User.query.filter_by(username='flora_fraz').first():
            admin = User(username='flora_fraz', password_hash=generate_password_hash('Flora]]12345'))
            db.session.add(admin)
            db.session.commit()
            print("👑 Администратор создан: flora_fraz / Flora]]12345")
        else:
            print("✅ Администратор flora_fraz уже существует")

    except Exception as e:
        print(f"Ошибка инициализации базы данных: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)