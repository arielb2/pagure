%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from
%distutils.sysconfig import get_python_lib; print (get_python_lib())")}

Name:           pagure
Version:        0.1.13
Release:        1%{?dist}
Summary:        A git-centered forge

License:        GPLv2+
URL:            http://fedorahosted.org/pagure/
Source0:        https://fedorahosted.org/releases/p/a/pagure/%{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python2-devel
BuildRequires:  python-setuptools
BuildRequires:  python-nose

BuildRequires:  python-alembic
BuildRequires:  python-arrow
BuildRequires:  python-blinker
BuildRequires:  python-chardet
BuildRequires:  python-docutils
BuildRequires:  python-flask
BuildRequires:  python-flask-wtf
BuildRequires:  python-markdown
BuildRequires:  python-psutil
BuildRequires:  python-pygit2 >= 0.20.1
BuildRequires:  python-pygments
BuildRequires:  python-fedora
BuildRequires:  python-openid
BuildRequires:  python-openid-cla
BuildRequires:  python-openid-teams
BuildRequires:  python-straight-plugin
BuildRequires:  python-wtforms
BuildRequires:  python-munch
BuildRequires:  python-enum34

# EPEL6
%if ( 0%{?rhel} && 0%{?rhel} == 6 )
BuildRequires:  python-sqlalchemy0.8
Requires:  python-sqlalchemy0.8
%else
BuildRequires:  python-sqlalchemy > 0.8
Requires:  python-sqlalchemy > 0.8
%endif

Requires:  python-alembic
Requires:  python-arrow
Requires:  python-blinker
Requires:  python-chardet
Requires:  python-docutils
Requires:  python-enum34
Requires:  python-flask
Requires:  python-flask-wtf
Requires:  python-markdown
Requires:  python-psutil
Requires:  python-pygit2 >= 0.20.1
Requires:  python-pygments
Requires:  python-fedora
Requires:  python-openid
Requires:  python-openid-cla
Requires:  python-openid-teams
Requires:  python-straight-plugin
Requires:  python-wtforms
Requires:  python-munch
Requires:  mod_wsgi

# No dependency of the app per se, but required to make it working.
Requires:  gitolite3


%description
Pagure is a light-weight git-centered forge based on pygit2.

Currently, Pagure offers a web-interface for git repositories, a ticket
system and possibilities to create new projects, fork existing ones and
create/merge pull-requests across or within projects.

%package milters
Summary:            Milter to integrate pagure with emails
BuildArch:          noarch
BuildRequires:      python-pymilter
BuildRequires:      systemd-devel
Requires:           python-pymilter
Requires(post):     systemd
Requires(preun):    systemd
Requires(postun):   systemd
# It would work with sendmail but we configure things (like the tempfile)
# to work with postfix
Requires:           postfix


%description milters
Milters (Mail filters) allowing the integration of pagure and emails.
This is useful for example to allow commenting on a ticket by email.


%prep
%setup -q


%build
%{__python2} setup.py build


%install
%{__python2} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT

# Install apache configuration file
mkdir -p $RPM_BUILD_ROOT/%{_sysconfdir}/httpd/conf.d/
install -m 644 files/pagure.conf $RPM_BUILD_ROOT/%{_sysconfdir}/httpd/conf.d/pagure.conf

# Install configuration file
mkdir -p $RPM_BUILD_ROOT/%{_sysconfdir}/pagure
install -m 644 files/pagure.cfg.sample $RPM_BUILD_ROOT/%{_sysconfdir}/pagure/pagure.cfg

# Install WSGI file
mkdir -p $RPM_BUILD_ROOT/%{_datadir}/pagure
install -m 644 files/pagure.wsgi $RPM_BUILD_ROOT/%{_datadir}/pagure/pagure.wsgi

# Install the createdb script
install -m 644 createdb.py $RPM_BUILD_ROOT/%{_datadir}/pagure/pagure_createdb.py

# Install the alembic configuration file
install -m 644 files/alembic.ini $RPM_BUILD_ROOT/%{_sysconfdir}/pagure/alembic.ini

# Install the alembic revisions
cp -r alembic $RPM_BUILD_ROOT/%{_datadir}/pagure


# Install the milter files
mkdir -p $RPM_BUILD_ROOT/%{_localstatedir}/run/pagure
mkdir -p $RPM_BUILD_ROOT/%{_tmpfilesdir}
mkdir -p $RPM_BUILD_ROOT/%{_unitdir}
install -m 0644 milters/milter_tempfile.conf \
    $RPM_BUILD_ROOT/%{_tmpfilesdir}/%{name}-milter.conf
install -m 644 milters/pagure_milter.service \
    $RPM_BUILD_ROOT/%{_unitdir}/pagure_milter.service
install -m 644 milters/comment_email_milter.py \
    $RPM_BUILD_ROOT/%{_datadir}/pagure/comment_email_milter.py


%post milters
%systemd_post pagure_milter.service

%preun milters
%systemd_preun pagure_milter.service

%postun milters
%systemd_postun_with_restart pagure_milter.service


%files
%doc README.rst
%license LICENSE
%config(noreplace) %{_sysconfdir}/httpd/conf.d/pagure.conf
%config(noreplace) %{_sysconfdir}/pagure/pagure.cfg
%config(noreplace) %{_sysconfdir}/pagure/alembic.ini
%dir %{_sysconfdir}/pagure/
%dir %{_datadir}/pagure/
%{_datadir}/pagure/pagure*
%{_datadir}/pagure/alembic/
%{python_sitelib}/pagure/
%{python_sitelib}/pagure*.egg-info


%files milters
%license LICENSE
%attr(755,postfix,postfix) %dir %{_localstatedir}/run/pagure
%dir %{_datadir}/pagure/
%{_tmpfilesdir}/%{name}-milter.conf
%{_unitdir}/pagure_milter.service
%{_datadir}/pagure/comment_email_milter.py*


%changelog
* Fri Jun 05 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.13-1
- Update to 0.1.13
- Do not show the edit button if the user cannot edit the file
- Fix who is allowed to drop comments
- Fix showing the drop comment button on issue comments
- Fix creating the pull-request for fast people like @lmacken
- Display the target of the PR as well as the origin in the PR page
- Limit the size of the lists on the front page

* Fri Jun 05 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.12-1
- Update to 0.1.12
- Fix the URL where the sources upload are done
- Upload the new sources under the project's name (be it project or
  user/project)

* Fri Jun 05 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.11-1
- Update to 0.1.11
- Another fix for the fedmsg_hook git hook
- Adjust how we display the README page to avoid XSS there as well
- Add the possibility to disable plugins via the configuration file
- Present the git tags in the UI
- As soon as the API user present a token, validate it or not, even if the
  endpoint would work without token
- Integrate alembic for DB scheme migration
- Cache the PR's merge status into the DB
- Only people with access to the project can add/remove API token
- Make the unit-tests run on bare repos as in prod
- First stab at online editing
- Simplify the API output to drop the project's settings where it doesn't
  make sense
- First stag at allowing upstream to upload their release to pagure
- Fix merging a PR into another branch than master
- Reduce code duplication when checking if a PR can be merged or merging it
- Code style clean-up

* Tue Jun 02 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.10-1
- Update to 0.1.10
- Add support for URL ending with a trailing slash where it makes sense (so
  we support both with and without trailing slash)
- Fix XSS issue by disabling <script> tags in the documentation pages
- Expend the unit-test suite for the api.project controller
- Add the possibility for 3rd party apps to 'flag' a pull-request with for
  example the result of a build
- Handle the situation where there are multiple branch of the same name in
  the same repo
- Fix the color of the link on hover when displayed within a tab view
  (for example in the PR pages)
- Redirect the user to the pull-request created after its the creation
- Do not leak emails over fedmsg
- Fix the fedmsg_hook plugin

* Fri May 29 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.9-1
- Update to 0.1.9
- Initial API work
- Document the initial API
- Fix the CSS to present the links correctly
- Add new API endpoint to list the git tags of a project
- Ensure the DB is updated regarding the start and stop commits before merging

* Wed May 27 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.8-1
- Update 0.1.8
- Add the possibility to do Asynchronous in-line comment posting
  (Patrick Uiterwijk)
- Handle the situation where the branch asked is not found in the git repo
- Handle the situation where we cannot find a desired commit
- Do not display a value in the settings page if there are none
- Rework the pull-request view to move the list of commits into a tab
- Make email sending optional (Patrick Uiterwijk)

* Fri May 22 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.7-1
- Update to 0.1.7
- Drop debugging code on the milter and the hooks
- Adjust the search_issues method to support filter for some tags, excluding
  some others (for example ?tags=easfix&tags=!0.2)
- Support groups when searching an user's projects (ie: finding the projects an
  user has access to via the group their are in)
- Do not load the git repo from the FS when loading an user's page
- Present and document the SSH keys in a dedicated documentation page

* Wed May 20 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.6-1
- Update to 0.1.6
- Fix sending notification emails to multiple users, avoid sending private into
  to all of them

* Tue May 19 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.5-1
- Update to 0.1.5
- Bug fix on the milter and the internal API endpoint

* Tue May 19 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.4-1
- Update to 0.1.4
- Fix loading requests and tickets from git (allows syncing projects between
  pagure instances)
- Add to the template .wsgi file a way to re-locate the tmp folder to work
  around a bug in libgit2
- Fix unit-tests suite
- Adjust the spec file to install all the files required for the milters
- Fix the `View` button on the pull-request pages

* Wed May 13 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.3-1
- Update to 0.1.3
- Add support for gitolite3
- Fix unit-tests suite to work on jenkins

* Sat May 09 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.2-2
- Fix the Requires on the milter subpackage (adding: post, preun and postun)
- Add systemd scriptlet to restart the service gracefully
- Use versioned python macro (py2)
- Ship the license in the milter subpackage as well
- Use the %%license macro

* Thu May 07 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.2-1
- Update to 0.1.2
- Fix bug in the fedmsg hook file (Thanks Zbigniew Jędrzejewski-Szmek)

* Wed May 06 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1.1-1
- Update to 0.1.1
- Port to python-munch and list it in the dependencies
- Fix exporting patch when they contain unicode characters or accent
- After creating an issue, user is brought back to the new issue page
- Fix unit-tests
- Stop the pagure hook if the user is deleting a branch (no need to run through
  all the commits of that branch)
- Fix the requirements.txt file (Sayan Chowdhury)
- Fix the tree page to show the commit sha on its proper line (Sayan Chowdhury)
- Fix typo in the form of some of the plugin (Sayan Chowdhury)
- Improve the README (Sayan Chowdhury)
- Fix highlighting the commits tab when accessing it (Sayan Chowdhury)

* Mon May 04 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.1-1
- First official release: 0.1

* Thu Apr 02 2015 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.0-1.20150402
- Cut a RPM for testing on Thu Apr 2nd 2015

* Wed Oct 08 2014 Pierre-Yves Chibon <pingou@pingoured.fr> - 0.0-1.20141008
- Initial packaging work for Fedora
