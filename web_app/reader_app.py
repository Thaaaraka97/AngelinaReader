#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
web application Sinhala Braille reader
"""
from flask import Flask, render_template, redirect, request, url_for, flash
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField, TextAreaField, HiddenField, SelectField
from wtforms.validators import DataRequired
from flask_mobility import Mobility
from flask_mobility.decorators import mobile_template

import time
import json
import argparse
from pathlib import Path

from .config import Config
from .reader_core import AngelinaSolver, VALID_EXTENTIONS


app = Flask(__name__)
Mobility(app)
app.config.from_object(Config)
login_manager = LoginManager(app)

data_root_path = Path(app.root_path) / app.config['DATA_ROOT']

core = AngelinaSolver(data_root_path=data_root_path)

@login_manager.user_loader
def load_user(user_id):
    return core.find_user(id=user_id)


@app.route("/", methods=['GET', 'POST'])
@app.route("/index", methods=['GET', 'POST'])
@mobile_template('{m/}index.html')
def index(template, is_mobile=False):
    class MainForm(FlaskForm):
        camera_file = FileField()
        file = FileField()
        agree = BooleanField("Agree")
        disgree = BooleanField("Disagree")
        lang = SelectField("Language", choices=[('RU', 'Sinahala')])
        find_orientation = BooleanField("Auto-orientation")
        process_2_sides = BooleanField("Both sides")
    form = MainForm(agree=request.values.get('has_public_confirm', 'True') == 'True',
                    disgree=request.values.get('has_public_confirm', '') == 'False',
                    lang=request.values.get('lang', 'RU'),
                    find_orientation=request.values.get('find_orientation', 'True') == 'True',
                    process_2_sides=request.values.get('process_2_sides', 'False') == 'True'
                    )
    if form.validate_on_submit():
        file_data = form.camera_file.data or form.file.data
        if not file_data:
            flash('Need to upload a file')
            return render_template(template, form=form)
        if form.agree.data and form.disgree.data or not form.agree.data and not form.disgree.data:
            flash('Choose one of the two options (agree / disagree)')
            return render_template(template, form=form)
        filename = file_data.filename
        file_ext = Path(filename).suffix[1:].lower()
        if file_ext not in VALID_EXTENTIONS:
            flash('Invalid file type {}: {}'.format(file_ext, filename))
            return render_template(template, form=form)

        user_id = current_user.get_id()
        extra_info = {'user': user_id,
                      'has_public_confirm': form.agree.data,
                      'lang': form.lang.data,
                      'find_orientation': form.find_orientation.data,
                      'process_2_sides': form.process_2_sides.data,
                      }
        task_id = core.process(user_id=user_id, file_storage=file_data, param_dict=extra_info)

        if not form.agree.data:
            return redirect(url_for('confirm',
                                    task_id=task_id,
                                    lang=form.lang.data,
                                    find_orientation=form.find_orientation.data,
                                    process_2_sides=form.process_2_sides.data))
        return redirect(url_for('results',
                                task_id=task_id,
                                has_public_confirm=form.agree.data,
                                lang=form.lang.data,
                                find_orientation=form.find_orientation.data,
                                process_2_sides=form.process_2_sides.data))

    return render_template(template, form=form)


@app.route("/confirm", methods=['GET', 'POST'])
@login_required
@mobile_template('{m/}confirm.html')
def confirm(template):
    class Form(FlaskForm):
        agree = BooleanField("I agree to the publication.")
        disgree = BooleanField("I object. This is private text.", default=True)
        submit = SubmitField('recognize')
    form = Form()
    if form.validate_on_submit():
        if form.agree.data and form.disgree.data or not form.agree.data and not form.disgree.data:
            flash('Choose one of the two options (agree / disagree)')
            return render_template(template, form=form)
        has_public_confirm = form.agree.data
        return redirect(url_for('results',
                                task_id=request.values['task_id'],
                                has_public_confirm=has_public_confirm,
                                lang=request.values['lang'],
                                find_orientation=request.values['find_orientation'],
                                process_2_sides=request.values['process_2_sides']))
    return render_template(template, form=form)


@app.route("/results", methods=['GET', 'POST'])
@login_required
@mobile_template('{m/}results.html')
def results(template):
    class ResultsForm(FlaskForm):
        results_list = HiddenField()
    form = ResultsForm()
    if form.validate_on_submit():
        return redirect(url_for('',
                                task_id=request.values['task_id'],
                                has_public_confirm=request.values['has_public_confirm'],
                                lang=request.values['lang'],
                                find_orientation=request.values['find_orientation'],
                                process_2_sides=request.values['process_2_sides']))
    results_list = None
    task_id = request.values['task_id']
    if task_id:
        assert core.is_completed(task_id, timeout=1)
        results_list = core.get_results(task_id)
    if results_list is None:
        flash(
            'File processing error. The file might be in the wrong format. If you think this is a mistake, please send the file to the address at the bottom of the page.')
        return redirect(url_for('index',
                                has_public_confirm=request.values['has_public_confirm'],
                                lang=request.values['lang'],
                                find_orientation=request.values['find_orientation'],
                                process_2_sides=request.values['process_2_sides']))
    # convert OS path to flask html path
    image_paths_and_texts = list()
    file_names = list()
    for marked_image_path, recognized_text_path, recognized_braille_path in results_list["item_data"]:
        # full path to image -> "/static/..."
        # data to display in the form

        # GVNC for Compatibility с V2: "/static/..." -> picture name
        marked_image_path = marked_image_path[1:]
        # marked_image_path = str(Path(marked_image_path).relative_to(app.config['DATA_ROOT']))
        # changes_presentation
        marked_image_path = str(Path(marked_image_path).relative_to(app.config['DATA_ROOT']))
        marked_image_path = marked_image_path.replace("marked", "labeled")
        print(marked_image_path)
        # print("Hi")
        
        recognized_text_path = str(Path(recognized_text_path).relative_to(data_root_path))
        recognized_braille_path = str(Path(recognized_braille_path).relative_to(data_root_path))

        with open(data_root_path / recognized_text_path, encoding="utf-8") as f:
            out_text = ''.join(f.readlines())
        with open(data_root_path / recognized_braille_path, encoding="utf-8") as f:
            out_braille = ''.join(f.readlines())
        image_paths_and_texts.append(("/" + app.config['DATA_ROOT'] + "/" + marked_image_path, out_text, out_braille,))

        # list with full paths to send to mail form
        file_names.append((str(data_root_path / marked_image_path), str(data_root_path / recognized_text_path)))  # list for

    form = ResultsForm(results_list=json.dumps(file_names))
    return render_template(template, form=form, image_paths_and_texts=image_paths_and_texts)

@app.route("/results_demo")
@mobile_template('{m/}results_demo.html')
def results_demo(template):
    time.sleep(1)
    return render_template(template)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

def run():
    parser = argparse.ArgumentParser(description='Sinhala Braille reader web app.')
    parser.add_argument('--debug', dest='debug', action='store_true',
                        help='enable debug mode (default: off)')
    args = parser.parse_args()
    debug = args.debug
    if not debug:
        # startup_logger()
        print("not debug")
    if debug:
        print('running in DEBUG mode!')
    else:
        print('running with no debug mode')
    app.jinja_env.cache = {}
    if debug:
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.run(debug=True, host='127.0.0.1', port=5001)
    else:
        app.run(host='127.0.0.1', threaded=True)

if __name__ == "__main__":
    run()