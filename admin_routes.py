from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import check_password_hash
from app import db, User, Phrase, TranslationLog
from datetime import datetime, timedelta
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('admin.admin_dashboard'))
        flash('Неверные данные')
    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))


@admin_bp.route('/')
@login_required
def admin_dashboard():
    total_phrases = Phrase.query.count()
    total_translations = TranslationLog.query.count()
    successful = TranslationLog.query.filter_by(success=True).count()
    success_rate = round((successful / total_translations * 100) if total_translations > 0 else 0)

    top_phrases = Phrase.query.order_by(Phrase.usage_count.desc()).limit(5).all()

    # Основные категории
    flower_count = Phrase.query.filter_by(plant_type='цветок').count()
    tree_count = Phrase.query.filter_by(plant_type='дерево').count()
    fruit_count = Phrase.query.filter_by(plant_type='фрукт').count()
    plant_count = Phrase.query.filter_by(plant_type='растение').count()
    grass_count = Phrase.query.filter_by(plant_type='трава').count()
    garden_count = Phrase.query.filter_by(plant_type='сад').count()

    # Дополнительные категории - ИСПРАВЛЕНО: используем 'бахча' вместо 'poliz'
    poliz_count = Phrase.query.filter_by(plant_type='бахча').count()  # ← изменено с 'poliz' на 'бахча'
    sabzavot_count = Phrase.query.filter_by(plant_type='овощ').count()
    bobovoe_rastenie_count = Phrase.query.filter_by(plant_type='бобовое_растение').count()
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
        'бобовое_растение_count': bobovoe_rastenie_count,
        'getreide_count': getreide_count
    }

    return render_template('admin/dashboard.html',
                           stats=stats,
                           top_phrases=top_phrases)


@admin_bp.route('/api/phrases', methods=['POST'])
@login_required
def add_phrase():
    data = request.json
    phrase = Phrase(
        german=data['german'],
        uzbek=data['uzbek'],
        literal=data.get('literal', ''),
        description=data.get('description', ''),
        notes=data.get('notes', ''),
        origin=data.get('origin', ''),
        example=data.get('example', ''),
        plant_type=data.get('plant_type', 'растение'),
        neutral_meaning=data.get('neutral_meaning', '')
    )
    db.session.add(phrase)
    db.session.commit()
    return jsonify({'success': True, 'id': phrase.id})


@admin_bp.route('/api/phrases/<int:phrase_id>', methods=['PUT'])
@login_required
def update_phrase(phrase_id):
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


@admin_bp.route('/api/phrases/<int:phrase_id>', methods=['DELETE'])
@login_required
def delete_phrase(phrase_id):
    phrase = Phrase.query.get_or_404(phrase_id)
    db.session.delete(phrase)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/statistics')
@login_required
def admin_statistics():
    daily_stats = []
    for i in range(7):
        date = datetime.utcnow().date() - timedelta(days=i)
        day_start = datetime.combine(date, datetime.min.time())
        day_end = datetime.combine(date, datetime.max.time())
        count = TranslationLog.query.filter(
            TranslationLog.timestamp.between(day_start, day_end)
        ).count()
        daily_stats.append({'date': date.isoformat(), 'count': count})

    return render_template('admin/statistics.html', daily_stats=daily_stats[::-1])