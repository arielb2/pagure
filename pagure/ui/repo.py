# -*- coding: utf-8 -*-

"""
 (c) 2014-2015 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""

import datetime
import shutil
import os
from math import ceil

import flask
import pygit2
import kitchen.text.converters as ktc
import werkzeug

from cStringIO import StringIO
from PIL import Image
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import guess_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound
from sqlalchemy.exc import SQLAlchemyError

import mimetypes
import chardet

import pagure.exceptions
import pagure.lib
import pagure.lib.git
import pagure.forms
import pagure
import pagure.ui.plugins
from pagure import (APP, SESSION, LOG, __get_file_in_tree, cla_required,
                    is_repo_admin, admin_session_timedout)

# pylint: disable=E1101


@APP.route('/<repo>/')
@APP.route('/<repo>')
@APP.route('/fork/<username>/<repo>/')
@APP.route('/fork/<username>/<repo>')
def view_repo(repo, username=None):
    """ Front page of a specific repo.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if repo is None:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    cnt = 0
    last_commits = []
    tree = []
    if not repo_obj.is_empty:
        try:
            for commit in repo_obj.walk(
                    repo_obj.head.target, pygit2.GIT_SORT_TIME):
                last_commits.append(commit)
                cnt += 1
                if cnt == 3:
                    break
            tree = sorted(last_commits[0].tree, key=lambda x: x.filemode)
        except pygit2.GitError:
            pass

    readme = None
    safe = False
    for i in tree:
        name, ext = os.path.splitext(i.name)
        if name == 'README':
            content = repo_obj[i.oid].data
            readme, safe = pagure.doc_utils.convert_readme(
                content, ext,
                view_file_url=flask.url_for(
                    'view_raw_file', username=username,
                    repo=repo.name, identifier='master', filename=''))

    diff_commits = []
    if repo.is_fork:
        parentname = os.path.join(
            APP.config['GIT_FOLDER'], repo.parent.path)
        if repo.parent.is_fork:
            parentname = os.path.join(
                APP.config['FORK_FOLDER'], repo.parent.path)
    else:
        parentname = os.path.join(APP.config['GIT_FOLDER'], repo.path)

    orig_repo = pygit2.Repository(parentname)

    if not repo_obj.is_empty and not orig_repo.is_empty:

        orig_branch = orig_repo.lookup_branch('master')
        branch = repo_obj.lookup_branch('master')
        if orig_branch and branch:

            master_commits = [
                commit.oid.hex
                for commit in orig_repo.walk(
                    orig_branch.get_object().hex,
                    pygit2.GIT_SORT_TIME)
            ]

            repo_commit = repo_obj[branch.get_object().hex]

            for commit in repo_obj.walk(
                    repo_commit.oid.hex, pygit2.GIT_SORT_TIME):
                if commit.oid.hex in master_commits:
                    break
                diff_commits.append(commit.oid.hex)

    return flask.render_template(
        'repo_info.html',
        select='overview',
        repo=repo,
        repo_obj=repo_obj,
        username=username,
        readme=readme,
        safe=safe,
        branches=sorted(repo_obj.listall_branches()),
        branchname='master',
        last_commits=last_commits,
        tree=tree,
        diff_commits=diff_commits,
        repo_admin=is_repo_admin(repo),
    )


@APP.route('/<repo>/branch/<path:branchname>')
@APP.route('/fork/<username>/<repo>/branch/<path:branchname>')
def view_repo_branch(repo, branchname, username=None):
    ''' Returns the list of branches in the repo. '''

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    if branchname not in repo_obj.listall_branches():
        flask.abort(404, 'Branch no found')

    branch = repo_obj.lookup_branch(branchname)

    cnt = 0
    last_commits = []
    for commit in repo_obj.walk(branch.get_object().hex, pygit2.GIT_SORT_TIME):
        last_commits.append(commit)
        cnt += 1
        if cnt == 10:
            break

    diff_commits = []
    if repo.is_fork:
        parentname = os.path.join(
            APP.config['GIT_FOLDER'], repo.parent.path)
        if repo.parent.is_fork:
            parentname = os.path.join(
                APP.config['FORK_FOLDER'], repo.parent.path)
    else:
        parentname = os.path.join(APP.config['GIT_FOLDER'], repo.path)

    orig_repo = pygit2.Repository(parentname)

    if not repo_obj.is_empty and not orig_repo.is_empty:

        master_branch = orig_repo.lookup_branch('master')
        master_commits = []

        if master_branch:
            master_commits = [
                commit.oid.hex
                for commit in orig_repo.walk(
                    master_branch.get_object().hex,
                    pygit2.GIT_SORT_TIME)
            ]

        repo_commit = repo_obj[branch.get_object().hex]

        for commit in repo_obj.walk(
                repo_commit.oid.hex, pygit2.GIT_SORT_TIME):
            if commit.oid.hex in master_commits:
                break
            diff_commits.append(commit.oid.hex)

    return flask.render_template(
        'repo_info.html',
        select='overview',
        repo=repo,
        username=username,
        branches=sorted(repo_obj.listall_branches()),
        branchname=branchname,
        last_commits=last_commits,
        tree=sorted(last_commits[0].tree, key=lambda x: x.filemode),
        diff_commits=diff_commits,
        repo_admin=is_repo_admin(repo),
    )


@APP.route('/<repo>/commits/')
@APP.route('/<repo>/commits')
@APP.route('/<repo>/commits/<path:branchname>')
@APP.route('/fork/<username>/<repo>/commits/')
@APP.route('/fork/<username>/<repo>/commits')
@APP.route('/fork/<username>/<repo>/commits/<path:branchname>')
def view_commits(repo, branchname=None, username=None):
    """ Displays the commits of the specified repo.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    if branchname and branchname not in repo_obj.listall_branches():
        flask.abort(404, 'Branch no found')

    if branchname:
        branch = repo_obj.lookup_branch(branchname)
    else:
        branch = repo_obj.lookup_branch('master')

    try:
        page = int(flask.request.args.get('page', 1))
    except ValueError:
        page = 1

    limit = APP.config['ITEM_PER_PAGE']
    start = limit * (page - 1)
    end = limit * page

    n_commits = 0
    last_commits = []
    if branch:
        for commit in repo_obj.walk(
                branch.get_object().hex, pygit2.GIT_SORT_TIME):
            if n_commits >= start and n_commits <= end:
                last_commits.append(commit)
            n_commits += 1

    total_page = int(ceil(n_commits / float(limit)))

    diff_commits = []
    if repo.is_fork:
        parentname = os.path.join(
            APP.config['GIT_FOLDER'], repo.parent.path)
        if repo.parent.is_fork:
            parentname = os.path.join(
                APP.config['FORK_FOLDER'], repo.parent.path)
    else:
        parentname = os.path.join(APP.config['GIT_FOLDER'], repo.path)

    orig_repo = pygit2.Repository(parentname)

    if not repo_obj.is_empty and not orig_repo.is_empty \
            and repo_obj.listall_branches() > 1:

        master_branch = orig_repo.lookup_branch('master')
        master_commits = []

        if master_branch:
            master_commits = [
                commit.oid.hex
                for commit in orig_repo.walk(
                    master_branch.get_object().hex,
                    pygit2.GIT_SORT_TIME)
            ]

        if branch:
            repo_commit = repo_obj[branch.get_object().hex]

            for commit in repo_obj.walk(
                    repo_commit.oid.hex, pygit2.GIT_SORT_TIME):
                if commit.oid.hex in master_commits:
                    break
                diff_commits.append(commit.oid.hex)

    origin = 'view_commits'

    return flask.render_template(
        'repo_info.html',
        select='logs',
        origin=origin,
        repo_obj=repo_obj,
        repo=repo,
        username=username,
        branches=sorted(repo_obj.listall_branches()),
        branchname=branchname,
        last_commits=last_commits,
        diff_commits=diff_commits,
        page=page,
        total_page=total_page,
        repo_admin=is_repo_admin(repo),
    )


@APP.route('/<repo>/blob/<path:identifier>/f/<path:filename>')
@APP.route('/fork/<username>/<repo>/blob/<path:identifier>/f/<path:filename>')
def view_file(repo, identifier, filename, username=None):
    """ Displays the content of a file or a tree for the specified repo.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    if repo_obj.is_empty:
        flask.abort(404, 'Empty repo cannot have a file')

    if identifier in repo_obj.listall_branches():
        branchname = identifier
        branch = repo_obj.lookup_branch(identifier)
        commit = branch.get_object()
    else:
        try:
            commit = repo_obj.get(identifier)
            branchname = identifier
        except ValueError:
            if 'master' not in repo_obj.listall_branches():
                flask.abort(404, 'Branch no found')
            # If it's not a commit id then it's part of the filename
            commit = repo_obj[repo_obj.head.target]
            branchname = 'master'

    if commit and not isinstance(commit, pygit2.Blob):
        content = __get_file_in_tree(
            repo_obj, commit.tree, filename.split('/'))
        if not content:
            flask.abort(404, 'File not found')
        content = repo_obj[content.oid]
    else:
        content = commit

    if isinstance(content, pygit2.Blob):
        if content.is_binary:
            ext = filename[filename.rfind('.'):]
            if ext in (
                    '.gif', '.png', '.bmp', '.tif', '.tiff', '.jpg',
                    '.jpeg', '.ppm', '.pnm', '.pbm', '.pgm', '.webp', '.ico'):
                try:
                    Image.open(StringIO(content.data))
                    output_type = 'image'
                except IOError as err:
                    LOG.debug(
                        'Failed to load image %s, error: %s', filename, err
                    )
                    output_type = 'binary'
            else:
                output_type = 'binary'
        else:
            try:
                lexer = guess_lexer_for_filename(
                    filename,
                    content.data
                )
            except ClassNotFound:
                lexer = TextLexer()

            content = highlight(
                content.data,
                lexer,
                HtmlFormatter(
                    noclasses=True,
                    style="tango",)
            )
            output_type = 'file'
    else:
        content = sorted(content, key=lambda x: x.filemode)
        output_type = 'tree'

    return flask.render_template(
        'file.html',
        select='tree',
        repo=repo,
        username=username,
        branchname=branchname,
        filename=filename,
        content=content,
        output_type=output_type,
        repo_admin=is_repo_admin(repo),
    )


@APP.route('/<repo>/raw/<path:identifier>', defaults={'filename': None})
@APP.route('/<repo>/raw/<path:identifier>/f/<path:filename>')
@APP.route('/fork/<username>/<repo>/raw/<path:identifier>',
           defaults={'filename': None})
@APP.route('/fork/<username>/<repo>/raw/<path:identifier>/f/<path:filename>')
def view_raw_file(repo, identifier, filename=None, username=None):
    """ Displays the raw content of a file of a commit for the specified repo.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    if repo_obj.is_empty:
        flask.abort(404, 'Empty repo cannot have a file')

    if identifier in repo_obj.listall_branches():
        branch = repo_obj.lookup_branch(identifier)
        commit = branch.get_object()
    else:
        try:
            commit = repo_obj.get(identifier)
        except ValueError:
            if 'master' not in repo_obj.listall_branches():
                flask.abort(404, 'Branch no found')
            # If it's not a commit id then it's part of the filename
            commit = repo_obj[repo_obj.head.target]

    if not commit:
        flask.abort(400, 'Commit %s not found' % (identifier))

    mimetype = None
    encoding = None
    if filename:
        content = __get_file_in_tree(
            repo_obj, commit.tree, filename.split('/'))
        if not content or isinstance(content, pygit2.Tree):
            flask.abort(404, 'File not found')

        mimetype, encoding = mimetypes.guess_type(filename)
        data = repo_obj[content.oid].data
    else:
        if commit.parents:
            diff = commit.tree.diff_to_tree()

            try:
                parent = repo_obj.revparse_single('%s^' % identifier)
                diff = repo_obj.diff(parent, commit)
            except (KeyError, ValueError):
                flask.abort(404, 'Identifier not found')
        else:
            # First commit in the repo
            diff = commit.tree.diff_to_tree(swap=True)
        data = diff.patch

    if not data:
        flask.abort(404, 'No content found')

    if not mimetype and data[:2] == '#!':
        mimetype = 'text/plain'

    if not mimetype:
        if '\0' in data:
            mimetype = 'application/octet-stream'
        else:
            mimetype = 'text/plain'

    if mimetype.startswith('text/') and not encoding:
        encoding = chardet.detect(ktc.to_bytes(data))['encoding']

    headers = {'Content-Type': mimetype}
    if encoding:
        headers['Content-Encoding'] = encoding

    return (data, 200, headers)


@APP.route('/<repo>/<commitid>/')
@APP.route('/<repo>/<commitid>')
@APP.route('/fork/<username>/<repo>/<commitid>/')
@APP.route('/fork/<username>/<repo>/<commitid>')
def view_commit(repo, commitid, username=None):
    """ Render a commit in a repo
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    try:
        commit = repo_obj.get(commitid)
    except ValueError:
        flask.abort(404, 'Commit not found')

    if commit is None:
        flask.abort(404, 'Commit not found')

    if commit.parents:
        diff = commit.tree.diff_to_tree()

        parent = repo_obj.revparse_single('%s^' % commitid)
        diff = repo_obj.diff(parent, commit)
    else:
        # First commit in the repo
        diff = commit.tree.diff_to_tree(swap=True)

    return flask.render_template(
        'commit.html',
        select='logs',
        repo=repo,
        username=username,
        commitid=commitid,
        commit=commit,
        diff=diff,
    )


@APP.route('/<repo>/<commitid>.patch')
@APP.route('/fork/<username>/<repo>/<commitid>.patch')
def view_commit_patch(repo, commitid, username=None):
    """ Render a commit in a repo as patch
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    try:
        commit = repo_obj.get(commitid)
    except ValueError:
        flask.abort(404, 'Commit not found')

    if commit is None:
        flask.abort(404, 'Commit not found')

    patch = pagure.lib.git.commit_to_patch(repo_obj, commit)

    return flask.Response(patch, content_type="text/plain;charset=UTF-8")


@APP.route('/<repo>/tree/')
@APP.route('/<repo>/tree')
@APP.route('/<repo>/tree/<path:identifier>')
@APP.route('/fork/<username>/<repo>/tree/')
@APP.route('/fork/<username>/<repo>/tree')
@APP.route('/fork/<username>/<repo>/tree/<path:identifier>')
def view_tree(repo, identifier=None, username=None):
    """ Render the tree of the repo
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if repo is None:
        flask.abort(404, 'Project not found')

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    branchname = None
    content = None
    output_type = None
    commit = None
    if not repo_obj.is_empty:
        if identifier in repo_obj.listall_branches():
            branchname = identifier
            branch = repo_obj.lookup_branch(identifier)
            commit = branch.get_object()
        else:
            try:
                commit = repo_obj.get(identifier)
                branchname = identifier
            except (ValueError, TypeError):
                # If it's not a commit id then it's part of the filename
                if 'master' in repo_obj.listall_branches():
                    commit = repo_obj[repo_obj.head.target]
                    branchname = 'master'

        if commit:
            content = sorted(commit.tree, key=lambda x: x.filemode)
        output_type = 'tree'

    return flask.render_template(
        'file.html',
        select='tree',
        repo_obj=repo_obj,
        repo=repo,
        username=username,
        branchname=branchname,
        filename='',
        content=content,
        output_type=output_type,
    )


@APP.route('/<repo>/forks/')
@APP.route('/<repo>/forks')
@APP.route('/fork/<username>/<repo>/forks/')
@APP.route('/fork/<username>/<repo>/forks')
def view_forks(repo, username=None):
    """ Presents all the forks of the project.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    return flask.render_template(
        'forks.html',
        select='forks',
        username=username,
        repo=repo,
    )


@APP.route('/<repo>/tags/')
@APP.route('/<repo>/tags')
@APP.route('/fork/<username>/<repo>/tags/')
@APP.route('/fork/<username>/<repo>/tags')
def view_tags(repo, username=None):
    """ Presents all the tags of the project.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    tags = pagure.lib.git.get_git_tags_objects(repo)

    return flask.render_template(
        'tags.html',
        select='tags',
        username=username,
        repo=repo,
        tags=tags,
        repo_admin=is_repo_admin(repo),
    )


@APP.route('/<repo>/upload/', methods=('GET', 'POST'))
@APP.route('/<repo>/upload', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/upload/', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/upload', methods=('GET', 'POST'))
def new_release(repo, username=None):
    """ Upload a new release.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    form = pagure.forms.UploadFileForm()

    if form.validate_on_submit():
        filestream = flask.request.files['filestream']
        filename = werkzeug.secure_filename(filestream.filename)
        try:
            folder = os.path.join(
                APP.config['UPLOAD_FOLDER_PATH'],
                werkzeug.secure_filename(repo.fullname))
            if not os.path.exists(folder):
                os.mkdir(folder)
            filestream.save(os.path.join(folder, filename))
            flask.flash('File uploaded')
        except Exception as err:  # pragma: no cover
            APP.logger.exception(err)
            flask.flash('Upload failed', 'error')
        return flask.redirect(
            flask.url_for('view_tags', repo=repo.name, username=username))

    return flask.render_template(
        'new_release.html',
        select='tags',
        username=username,
        repo=repo,
        form=form,
    )


@APP.route('/<repo>/settings/', methods=('GET', 'POST'))
@APP.route('/<repo>/settings', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/settings/', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/settings', methods=('GET', 'POST'))
@cla_required
def view_settings(repo, username=None):
    """ Presents the settings of the project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    plugins = pagure.ui.plugins.get_plugin_names(
        APP.config.get('DISABLED_PLUGINS'))
    tags = pagure.lib.get_tags_of_project(SESSION, repo)

    form = pagure.forms.ConfirmationForm()
    tag_form = pagure.forms.AddIssueTagForm()

    if form.validate_on_submit():
        settings = {}
        for key in flask.request.form:
            if key == 'csrf_token':
                continue
            settings[key] = flask.request.form[key]

        try:
            message = pagure.lib.update_project_settings(
                SESSION,
                repo=repo,
                settings=settings,
                user=flask.g.fas_user.username,
            )
            SESSION.commit()
            flask.flash(message)
            return flask.redirect(flask.url_for(
                'view_repo', username=username, repo=repo.name))
        except SQLAlchemyError, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.render_template(
        'settings.html',
        select='settings',
        username=username,
        repo=repo,
        form=form,
        tag_form=tag_form,
        tags=tags,
        plugins=plugins,
    )


@APP.route('/<repo>/updatedesc', methods=['POST'])
@APP.route('/fork/<username>/<repo>/updatedesc', methods=['POST'])
@cla_required
def update_description(repo, username=None):
    """ Update the description of a project.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    form = pagure.forms.DescriptionForm()

    if form.validate_on_submit():
        avatar_email = form.avatar_email.data \
            if form.avatar_email.data and form.avatar_email.data.strip() \
            else None
        try:
            repo.description = form.description.data
            repo.avatar_email = avatar_email
            SESSION.add(repo)
            SESSION.commit()
            flask.flash('Project updated')
        except SQLAlchemyError, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.redirect(flask.url_for(
        'view_settings', username=username, repo=repo.name))


@APP.route('/<repo>/delete', methods=['POST'])
@APP.route('/fork/<username>/<repo>/delete', methods=['POST'])
@cla_required
def delete_repo(repo, username=None):
    """ Delete the present project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    try:
        for issue in repo.issues:
            for comment in issue.comments:
                SESSION.delete(comment)
            SESSION.commit()
            SESSION.delete(issue)
        SESSION.delete(repo)
        SESSION.commit()
    except SQLAlchemyError, err:  # pragma: no cover
        SESSION.rollback()
        APP.logger.exception(err)
        flask.flash('Could not delete the project', 'error')

    repopath = os.path.join(APP.config['GIT_FOLDER'], repo.path)
    if repo.is_fork:
        repopath = os.path.join(APP.config['FORK_FOLDER'], repo.path)
    docpath = os.path.join(APP.config['DOCS_FOLDER'], repo.path)
    ticketpath = os.path.join(APP.config['TICKETS_FOLDER'], repo.path)
    requestpath = os.path.join(APP.config['REQUESTS_FOLDER'], repo.path)

    try:
        shutil.rmtree(repopath)
        shutil.rmtree(docpath)
        shutil.rmtree(ticketpath)
        shutil.rmtree(requestpath)
    except (OSError, IOError), err:
        APP.logger.exception(err)
        flask.flash(
            'Could not delete all the repos from the system', 'error')

    return flask.redirect(
        flask.url_for('view_user', username=flask.g.fas_user.username))


@APP.route('/<repo>/hook_token', methods=['POST'])
@APP.route('/fork/<username>/<repo>/hook_token', methods=['POST'])
@cla_required
def new_repo_hook_token(repo, username=None):
    """ Re-generate a hook token for the present project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    form = pagure.forms.ConfirmationForm()
    if not form.validate_on_submit():
        flask.abort(400, 'Invalid request')

    try:
        repo.hook_token = pagure.lib.login.id_generator(40)
        SESSION.commit()
        flask.flash('New hook token generated')
    except SQLAlchemyError, err:  # pragma: no cover
        SESSION.rollback()
        APP.logger.exception(err)
        flask.flash('Could not generate a new token for this project', 'error')

    return flask.redirect(
        flask.url_for('view_settings', repo=repo.name, username=username))


@APP.route('/<repo>/dropuser/<userid>', methods=['POST'])
@APP.route('/fork/<username>/<repo>/dropuser/<userid>', methods=['POST'])
@cla_required
def remove_user(repo, userid, username=None):
    """ Remove the specified user from the project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the users for this project')

    form = pagure.forms.ConfirmationForm()
    if form.validate_on_submit():
        userids = [str(user.id) for user in repo.users]

        if str(userid) not in userids:
            flask.flash(
                'User does not have commit or cannot loose it right', 'error')
            return flask.redirect(
                flask.url_for(
                    '.view_settings', repo=repo.name, username=username)
            )

        for user in repo.users:
            if str(user.id) == str(userid):
                repo.users.remove(user)
                break
        try:
            SESSION.commit()
            pagure.generate_gitolite_acls()
            flask.flash('User removed')
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            flask.flash('User could not be removed', 'error')

    return flask.redirect(
        flask.url_for('.view_settings', repo=repo.name, username=username)
    )


@APP.route('/<repo>/adduser/', methods=('GET', 'POST'))
@APP.route('/<repo>/adduser', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/adduser/', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/adduser', methods=('GET', 'POST'))
@cla_required
def add_user(repo, username=None):
    """ Add the specified user from the project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to add users to this project')

    form = pagure.forms.AddUserForm()

    if form.validate_on_submit():
        try:
            msg = pagure.lib.add_user_to_project(
                SESSION, repo,
                new_user=form.user.data,
                user=flask.g.fas_user.username,
            )
            SESSION.commit()
            pagure.generate_gitolite_acls()
            flask.flash(msg)
            return flask.redirect(
                flask.url_for(
                    '.view_settings', repo=repo.name, username=username)
            )
        except pagure.exceptions.PagureException as msg:
            SESSION.rollback()
            flask.flash(msg, 'error')
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            flask.flash('User could not be added', 'error')

    return flask.render_template(
        'add_user.html',
        form=form,
        username=username,
        repo=repo,
    )


@APP.route('/<repo>/addgroup/', methods=('GET', 'POST'))
@APP.route('/<repo>/addgroup', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/addgroup/', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/addgroup', methods=('GET', 'POST'))
@cla_required
def add_group_project(repo, username=None):
    """ Add the specified group from the project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to add groups to this project')

    form = pagure.forms.AddGroupForm()

    if form.validate_on_submit():
        try:
            msg = pagure.lib.add_group_to_project(
                SESSION, repo,
                new_group=form.group.data,
                user=flask.g.fas_user.username,
            )
            SESSION.commit()
            pagure.generate_gitolite_acls()
            flask.flash(msg)
            return flask.redirect(
                flask.url_for(
                    '.view_settings', repo=repo.name, username=username)
            )
        except pagure.exceptions.PagureException as msg:
            SESSION.rollback()
            flask.flash(msg, 'error')
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            flask.flash('Group could not be added', 'error')

    return flask.render_template(
        'add_group_project.html',
        form=form,
        username=username,
        repo=repo,
    )


@APP.route('/<repo>/regenerate', methods=['POST'])
@APP.route('/fork/<username>/<repo>/regenerate', methods=['POST'])
@cla_required
def regenerate_git(repo, username=None):
    """ Regenerate the specified git repo with the content in the project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(403, 'You are not allowed to regenerate the git repos')

    regenerate = flask.request.form.get('regenerate')
    if not regenerate or regenerate.lower() not in ['tickets', 'requests']:
        flask.abort(400, 'You can only regenerate tickest or requests repos')

    form = pagure.forms.ConfirmationForm()
    if form.validate_on_submit():
        if regenerate.lower() == 'requests':
            for request in repo.requests:
                pagure.lib.git.update_git(
                    request, repo=repo,
                    repofolder=APP.config['REQUESTS_FOLDER'])
            flask.flash('Requests git repo updated')
        elif regenerate.lower() == 'tickets':
            for ticket in repo.issues:
                # Do not store private issues in the git
                if ticket.private:
                    continue
                pagure.lib.git.update_git(
                    ticket, repo=repo,
                    repofolder=APP.config['TICKETS_FOLDER'])
            flask.flash('Tickets git repo updated')

    return flask.redirect(
        flask.url_for('.view_settings', repo=repo.name, username=username)
    )


@APP.route('/<repo>/token/new/', methods=('GET', 'POST'))
@APP.route('/<repo>/token/new', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/token/new/', methods=('GET', 'POST'))
@APP.route('/fork/<username>/<repo>/token/new', methods=('GET', 'POST'))
@cla_required
def add_token(repo, username=None):
    """ Add a token to a specified project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    acls = pagure.lib.get_acls(SESSION)
    form = pagure.forms.NewTokenForm(acls=acls)

    if form.validate_on_submit():
        try:
            msg = pagure.lib.add_token_to_user(
                SESSION,
                repo,
                acls=form.acls.data,
                username=flask.g.fas_user.username,
            )
            SESSION.commit()
            flask.flash(msg)
            return flask.redirect(
                flask.url_for(
                    '.view_settings', repo=repo.name, username=username)
            )
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            flask.flash('User could not be added', 'error')

    return flask.render_template(
        'add_token.html',
        form=form,
        acls=acls,
        username=username,
        repo=repo,
    )


@APP.route('/<repo>/token/revoke/<token_id>', methods=['POST'])
@APP.route('/fork/<username>/<repo>/token/revoke/<token_id>',
           methods=['POST'])
@cla_required
def revoke_api_token(repo, token_id, username=None):
    """ Revokie a token to a specified project.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    token = pagure.lib.get_api_token(SESSION, token_id)

    if not token \
            or token.project.fullname != repo.fullname \
            or token.user.username != flask.g.fas_user.username:
        flask.abort(404, 'Token not found')

    form = pagure.forms.ConfirmationForm()

    if form.validate_on_submit():
        try:
            token.expiration = datetime.datetime.utcnow()
            SESSION.commit()
            flask.flash('Token revoked')
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            flask.flash(
                'Token could not be revoked, please contact an admin',
                'error')

    return flask.redirect(
        flask.url_for(
            '.view_settings', repo=repo.name, username=username)
    )


@APP.route(
    '/<repo>/edit/<path:branchname>/f/<path:filename>',
    methods=('GET', 'POST'))
@APP.route(
    '/fork/<username>/<repo>/edit/<path:branchname>/f/<path:filename>',
    methods=('GET', 'POST'))
@cla_required
def edit_file(repo, branchname, filename, username=None):
    """ Edit a file online.
    """
    repo = pagure.lib.get_project(SESSION, repo, user=username)

    if not repo:
        flask.abort(404, 'Project not found')

    if not is_repo_admin(repo):
        flask.abort(
            403,
            'You are not allowed to change the settings for this project')

    user = pagure.lib.search_user(
        SESSION, username=flask.g.fas_user.username)

    reponame = pagure.get_repo_path(repo)

    repo_obj = pygit2.Repository(reponame)

    if repo_obj.is_empty:
        flask.abort(404, 'Empty repo cannot have a file')

    branch = None
    if branchname in repo_obj.listall_branches():
        branch = repo_obj.lookup_branch(branchname)
        commit = branch.get_object()
    else:
        flask.abort(400, 'Invalid branch specified')

    form = pagure.forms.EditFileForm(emails=user.emails)
    if form.validate_on_submit():
        try:
            pagure.lib.git.update_file_in_git(
                repo,
                branch=branchname,
                filename=filename,
                content=form.content.data,
                message='%s\n\n%s' % (
                    form.commit_title.data.strip(),
                    form.commit_message.data.strip()
                ),
                user=flask.g.fas_user,
                email=form.email.data,
            )
            flask.flash('Changes committed')
            return flask.redirect(
                flask.url_for(
                    '.view_file', repo=repo.name, username=username,
                    identifier=branchname, filename=filename)
            )
        except pagure.exceptions.PagureException as err:  # pragma: no cover
            APP.logger.exception(err)
            flask.flash('Commit could not be done', 'error')
            data = form.content.data
    elif flask.request.method == 'GET':
        content = __get_file_in_tree(
            repo_obj, commit.tree, filename.split('/'))
        if not content or isinstance(content, pygit2.Tree):
            flask.abort(404, 'File not found')
        if content.is_binary:
            flask.abort(400, 'Cannot edit binary files')
        data = repo_obj[content.oid].data
    else:
        data = form.content.data

    return flask.render_template(
        'edit_file.html',
        select='tree',
        repo=repo,
        username=username,
        branchname=branchname,
        data=data,
        filename=filename,
        form=form,
        user=user,
    )
