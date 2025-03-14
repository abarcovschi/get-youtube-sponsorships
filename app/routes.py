from web_main import app
from flask import render_template, request, session
from app.forms import MultipleVideosForm, SingleVideoForm
from flask import render_template, flash, redirect, url_for
from main import by_channel, by_video


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def multiple_videos():
    form = MultipleVideosForm()
    if form.validate_on_submit():
        flash('Sponsorships requested for channel {}, number of most recent videos={}'.format(
            form.handle.data, form.num_vids.data))
        if form.num_vids.data < 1:
            flash('Number of videos must be more than 1. Please try again.', 'error')
            return render_template('multiple_videos.html', title="Get Sponsorships From Channel", form=form)
        data = by_channel(form.handle.data, form.num_vids.data)
        if not data:  # Check if 'data' is empty
            flash('Channel not found. Please check the handle and try again.', 'error')
            return render_template('multiple_videos.html', title="Get Sponsorships From Channel", form=form)
        # Store data in session or pass it as URL parameters
        session['channel_data'] = data
        return redirect(url_for('multiple_videos_result'))
    return render_template('multiple_videos.html', title="Get Sponsorships From Channel", form=form)


@app.route('/video', methods=['GET', 'POST'])
def single_video():
    form = SingleVideoForm()
    if form.validate_on_submit():
        flash('Sponsorships requested for video {}'.format(form.url.data))
        data = by_video(form.url.data)
        if not data.get('sponsorships'):  # Check if 'data' is empty
            flash('Incorrect URL. Please check the URL and try again.', 'error')
            return render_template('single_video.html', title="Get Sponsorships From Video", form=form)
        # Store data in session or pass it as URL parameters
        session['video_data'] = data
        return redirect(url_for('single_video_result'))
    return render_template('single_video.html', title="Get Sponsorships From Video", form=form)


@app.route('/multiple_videos_result', methods=['GET', 'POST'])
def multiple_videos_result():
    data = session.get('channel_data', [])  # Retrieve data from session
    return render_template('multiple_videos_result.html', data=data)


@app.route('/single_video_result', methods=['GET', 'POST'])
def single_video_result():
    data = session.get('video_data', [])  # Retrieve data from session
    return render_template('single_video_result.html', data=data)