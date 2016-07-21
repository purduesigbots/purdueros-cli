import click
from functools import lru_cache
import tempfile
import os
import os.path
import proscli.utils
from prosconductor.providers import TemplateTypes, DepotProvider, InvalidIdentifierException, DepotConfig, Identifier, \
    get_template_dir
import re
import requests
import shutil
from typing import List, Dict, Set
import zipfile


class GithubReleasesDepotProvider(DepotProvider):
    registrar = 'github-releases'

    def __init__(self, config: DepotConfig):
        super(GithubReleasesDepotProvider, self).__init__(config)

    def create_headers(self, accept='application/vnd.github.v3+json'):
        headers = {'user-agent': 'purdueros-cli', 'Accept': accept}
        if 'oauth_token' in self.config.registrar_options:
            headers['Authorization'] = 'token {}'.format(self.config.registrar_options['oauth_token'])
        return headers

    def verify_configuration(self):
        if not re.fullmatch(pattern='[A-z0-9](?:-?[A-z0-9]){0,38}\/[0-9A-z_\.-]{1,93}', string=self.config.location):
            raise InvalidIdentifierException('{} is an invalid GitHub resository'.format(self.config.location))

    @staticmethod
    def configure_registar_options():
        options = dict()
        options['include_prerelease'] = click.prompt('Include pre-releases?', default=False, prompt_suffix=' ')
        options['include_draft'] = click.prompt('Include drafts (requires authentication)?',
                                                default=False, prompt_suffix=' ')
        if click.confirm('Do you want to set up OAuth authentication with GitHub?'):
            options['oauth_token'] = click.prompt('OAuth2 Token:', prompt_suffix=' ')
        return options

    def list_all(self, template_types: List[TemplateTypes] = None):
        self.verify_configuration()
        if template_types is None:
            template_types = [TemplateTypes.kernel, TemplateTypes.library]
        config = self.config
        proscli.utils.debug('Fetching listing for {} at {} using {}'.format(config.name, config.location, self.registrar))
        r = requests.get('https://api.github.com/repos/{}/releases'.format(config.location),
                         headers=self.create_headers())
        if r.status_code == 200:
            response = dict()  # type: Dict[TemplateTypes, Set[Identifier]]
            json = r.json()
            # filter out pre-releases according to registar_options (include_prerelease implies prerelease) and
            # by if the release has a kernel-template.zip or library-template.zip file
            for release in [rel for rel in json if
                            (not rel['prerelease'] or config.registrar_options.get('include_prerelease', False)) and
                            (not rel['draft'] or config.registrar_options.get('include_draft', False))]:
                for asset in [a for a in release['assets'] if
                              re.fullmatch(string=a['name'].lower(), pattern='.*-template.zip')]:
                    if asset['name'].lower() == 'kernel-template.zip' and TemplateTypes.kernel in template_types:
                        if TemplateTypes.kernel not in response:
                            response[TemplateTypes.kernel] = set()
                        response[TemplateTypes.kernel].add(Identifier(name='kernel', version=release['tag_name']))
                    elif TemplateTypes.library in template_types:
                        # if the name isn't kernel-template.zip, then it's a library
                        if TemplateTypes.library not in response:
                            response[TemplateTypes.library] = set()
                        response[TemplateTypes.library].add(
                            Identifier(name=asset['name'][:-len('-template.zip')], version=release['tag_name']))

            return response
        else:
            click.echo('Unable to get listing for {} at {}'.format(config.name, config.location))
            proscli.utils.debug(r.__dict__)
            return dict()

    def download(self, identifier: Identifier) -> bool:
        self.verify_configuration()
        template_dir = get_template_dir(self, identifier)
        if os.path.isdir(template_dir):
            shutil.rmtree(template_dir)
        elif os.path.isfile(template_dir):
            os.remove(template_dir)
        # verify release exists:
        click.echo('Fetching release on {} with tag {}'.format(self.config.location, identifier.version))
        r = requests.get('https://api.github.com/repos/{}/releases/tags/{}'.format(self.config.location,
                                                                                   identifier.version),
                         headers=self.create_headers())
        if r.status_code == 200:
            for asset in [a for a in r.json()['assets'] if a['name'] == '{}-template.zip'.format(identifier.name)]:
                # Time to download the file
                proscli.utils.debug('Found {}'.format(asset['url']))
                dr = requests.get(asset['url'], headers=self.create_headers('application/octet-stream'), stream=True)
                if dr.status_code == 200 or dr.status_code == 302:
                    with tempfile.NamedTemporaryFile(delete=False) as tf:
                        # todo: no temp file necessary - go straight from download to zipfile extraction
                        with click.progressbar(length=asset['size'],
                                               label='Downloading {} (v: {})'.format(asset['name'],
                                                                                     identifier.version)) \
                                as progress_bar:
                            for chunk in dr.iter_content(128):
                                tf.write(chunk)
                                progress_bar.update(128)
                        tf.close()  # need to close since opening again as ZipFile
                        with zipfile.ZipFile(tf.name) as zf:
                            with click.progressbar(length=len(zf.namelist()),
                                                   label='Extracting {}'.format(asset['name'])) as progress_bar:
                                for file in zf.namelist():
                                    zf.extract(file, path=template_dir)
                                    progress_bar.update(1)
                        os.remove(tf.name)
                    click.echo('Template downloaded to {}'.format(template_dir))
                    return True
                else:
                    click.echo('Unable to download {} from {} (Status code: {})'.format(asset['name'],
                                                                                        self.config.location,
                                                                                        dr.status_code))
                    proscli.utils.debug(dr.__dict__)
                    return False
        else:
            click.echo('Unable to find {} on {} (Status code: {})'.format(identifier.version,
                                                                          self.config.name,
                                                                          r.status_code))
            proscli.utils.debug(r.__dict__)
            return False