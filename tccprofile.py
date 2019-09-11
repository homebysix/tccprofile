#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import datetime
import errno
import os
import plistlib
import pytz
import re
import uuid
import subprocess
import sys
import Tkinter as tk
import ttk
import tkFileDialog

# Imports specifically for FoundationPlist
# PyLint cannot properly find names inside Cocoa libraries, so issues bogus
# No name 'Foo' in module 'Bar' warnings. Disable them.
# pylint: disable=E0611
import AppKit
from Foundation import NSData  # NOQA
from Foundation import NSPropertyListSerialization  # NOQA
from Foundation import NSPropertyListMutableContainers  # NOQA
from Foundation import NSPropertyListXMLFormat_v1_0  # NOQA
# pylint: enable=E0611

# Script details
__author__ = ['Carl Windus', 'Bryson Tyrrell']
__license__ = 'Apache License 2.0'
__version__ = '1.1.0.01'
__date__ = '2019-09-11-1904'

VERSION_STRING = 'Version: {} [{}] ({}), Authors: {}'.format(__version__, __date__, __license__, ', '.join(__author__))


# Special thanks to the munki crew for the plist work.
# FoundationPlist from munki
class FoundationPlistException(Exception):
    """Basic exception for plist errors"""
    pass


class NSPropertyListSerializationException(FoundationPlistException):
    """Read/parse error for plists"""
    pass


class TCCProfileException(Exception):
    """Base exception for script errors"""
    pass


class App(tk.Frame):
    def __init__(self, master):
        tk.Frame.__init__(self, master)
        self.pack()
        self.master.title("TCC Profile Generator")
        self.master.resizable(False, False)
        self.master.tk_setPalette(background='#ececec')

        self.master.protocol('WM_DELETE_WINDOW', self.click_quit)
        self.master.bind('<Return>', self.click_save)

        x = (self.master.winfo_screenwidth() - self.master.winfo_reqwidth()) / 2
        y = (self.master.winfo_screenheight() - self.master.winfo_reqheight()) / 4
        self.master.geometry("+{}+{}".format(x, y))

        self.master.config(menu=tk.Menu(self.master))

        # Payload Details UI

        payload_frame = tk.Frame(self)
        payload_frame.pack(padx=15, pady=15, fill=tk.BOTH)

        tk.Label(
            payload_frame,
            text='Payload Details',
            font=('System', 18)
        ).grid(row=0, column=0, columnspan=5, sticky='w')

        tk.Label(payload_frame, text="Name").grid(
            row=1, column=0, sticky='w'
        )
        self._payload_name = tk.Entry(payload_frame, bg='white', width=30)
        self._payload_name.insert(0, 'TCC Whitelist')
        self._payload_name.grid(row=2, column=0, columnspan=2, sticky='we')

        # This is an empty spacer for the grid layout of the frame
        tk.Label(
            payload_frame,
            text='',
            width=6
        ).grid(row=1, column=2)

        tk.Label(payload_frame, text="Organization").grid(
            row=1, column=3, sticky='w'
        )
        self._payload_org = tk.Entry(payload_frame, bg='white', width=30)
        self._payload_org.insert(0, 'My Org Name')
        self._payload_org.grid(row=2, column=3, columnspan=2, sticky='we')

        tk.Label(payload_frame, text="Identifier").grid(
            row=3, column=0, sticky='w'
        )
        self._payload_id = tk.Entry(payload_frame, bg='white')
        self._payload_id.insert(0, 'com.my.tccprofile')
        self._payload_id.grid(row=4, column=0, columnspan=2, sticky='we')

        tk.Label(payload_frame, text="Description").grid(
            row=5, column=0, sticky='w'
        )
        self._payload_desc = tk.Entry(payload_frame, bg='white')
        self._payload_desc.insert(0, 'TCC Whitelist for various applications')
        self._payload_desc.grid(row=6, column=0, columnspan=5, sticky='we')

        self._payload_sign = tk.StringVar()
        self._payload_sign.set('No')

        tk.Label(payload_frame, text="Sign Profile?").grid(
            row=7, column=0, sticky='e'
        )
        tk.OptionMenu(
            payload_frame,
            self._payload_sign,
            *self._list_signing_certs()
        ).grid(row=7, column=1, columnspan=4, sticky='we')

        # UI Feedback Section

        feedback_frame = tk.Frame(self)
        feedback_frame.pack(padx=15, fill=tk.BOTH)

        self._feedback_label = tk.Label(
            feedback_frame,
            font=("System", 12, "italic"),
            fg='red'
        )
        self._feedback_label.grid(row=0, column=0, sticky='we')

        # Services UI

        services_frame = tk.Frame(self)
        services_frame.pack(padx=15, pady=15, fill=tk.BOTH)

        self._services_target_var = tk.StringVar()
        self._services_target_var_display = tk.StringVar()

        tk.Label(
            services_frame,
            text='Setup Service Permissions',
            font=('System', 18)
        ).grid(row=0, column=0, columnspan=5, sticky='w')

        tk.Label(services_frame, text="Target App...").grid(
            row=1, column=0, sticky='w'
        )
        self.app_env_source_btn = tk.Button(
            services_frame,
            text='Choose...',
            command=lambda: self._app_picker('_services_target_var')
        )
        self.app_env_source_btn.grid(row=2, column=0, sticky='w')

        tk.Label(
            services_frame,
            textvariable=self._services_target_var_display,
            width=20
        ).grid(row=2, column=1, sticky='w')

        self._available_services = {
            'AddressBook': True,
            'Calendar': True,
            'Reminders': True,
            'Photos': True,
            'Camera': False,
            'Microphone': False,
            'Accessibility': True,
            'PostEvent': True,
            'SystemPolicyAllFiles': True,
            'SystemPolicySysAdminFiles': True
        }

        self._selected_service = tk.StringVar()
        self._selected_service.set('AddressBook')

        tk.Label(services_frame, text="Service...").grid(
            row=1, column=2, sticky='w'
        )
        tk.OptionMenu(
            services_frame,
            self._selected_service,
            *sorted([i for i in self._available_services.keys()])
        ).grid(row=2, column=2, sticky='w')

        # This is an empty spacer for the grid layout of the frame
        tk.Label(
            services_frame,
            text='',
            width=14
        ).grid(row=2, column=3)

        tk.Button(
            services_frame,
            text='Add +',
            command=self._add_service
        ).grid(row=2, column=4, sticky='e')

        self.services_table = ttk.Treeview(
            services_frame,
            columns=('target', 'service', 'allow_deny'),
            height=5
        )
        self.services_table['show'] = 'headings'

        self.services_table.heading('target', text='Target')

        self.services_table.heading('service', text='Service')
        self.services_table.column('service', anchor='center')

        self.services_table.heading('allow_deny', text='Allow/Deny')
        self.services_table.column('allow_deny', anchor='center')

        self.services_table.grid(row=3, column=0, columnspan=5, sticky='we')

        tk.Button(
            services_frame,
            text='Remove -',
            command=lambda: self._remove_table_item('services_table')
        ).grid(row=4, column=4, sticky='e')

        # Apple Events UI

        apple_events_frame = tk.Frame(self)
        apple_events_frame.pack(padx=15, pady=15, fill=tk.BOTH)

        self._app_env_source_var = tk.StringVar()
        self._app_env_target_var = tk.StringVar()
        self._app_env_source_var_display = tk.StringVar()
        self._app_env_target_var_display = tk.StringVar()

        tk.Label(
            apple_events_frame,
            text='Setup Apple Events',
            font=('System', 18)
        ).grid(row=0, column=0, columnspan=5, sticky='w')

        tk.Label(apple_events_frame, text="Source App...").grid(
            row=1, column=0, sticky='w'
        )

        self.app_env_source_btn = tk.Button(
            apple_events_frame,
            text='Choose...',
            command=lambda: self._app_picker('_app_env_source_var')
        )
        self.app_env_source_btn.grid(row=2, column=0, sticky='w')

        tk.Label(
            apple_events_frame,
            textvariable=self._app_env_source_var_display,
            width=20
        ).grid(row=2, column=1, sticky='w')

        tk.Label(apple_events_frame, text="Target App...").grid(
            row=1, column=2, sticky='w'
        )

        self.app_env_target_btn = tk.Button(
            apple_events_frame,
            text='Choose...',
            command=lambda: self._app_picker('_app_env_target_var')
        )
        self.app_env_target_btn.grid(row=2, column=2, sticky='w')

        tk.Label(
            apple_events_frame,
            textvariable=self._app_env_target_var_display,
            width=20
        ).grid(row=2, column=3, sticky='w')

        tk.Button(
            apple_events_frame,
            text='Add +',
            command=self._add_apple_event
        ).grid(row=2, column=4, sticky='e')

        self.app_env_table = ttk.Treeview(
            apple_events_frame, columns=('source', 'target'), height=5
        )
        self.app_env_table['show'] = 'headings'
        self.app_env_table.heading('source', text='Source')
        self.app_env_table.heading('target', text='Target')
        self.app_env_table.grid(row=3, column=0, columnspan=5, sticky='we')

        tk.Button(
            apple_events_frame,
            text='Remove -',
            command=lambda: self._remove_table_item('app_env_table')
        ).grid(row=4, column=4, sticky='e')

        # Bottom frame for "Save' and 'Quit' buttons
        button_frame = tk.Frame(self)
        button_frame.pack(padx=15, pady=(0, 15), anchor='e')

        tk.Button(button_frame, text='Save', command=self.click_save).pack(
            side='right'
        )
        tk.Button(button_frame, text='Quit', command=self.click_quit).pack(
            side='right'
        )

    def click_save(self, event=None):
        print("The user clicked 'Save'")

        payload = dict()
        payload['Description'] = self._payload_desc.get()
        payload['Name'] = self._payload_name.get()
        payload['Identifier'] = self._payload_id.get()
        payload['Organization'] = self._payload_org.get()

        for k, v in payload.items():
            if not v:
                self._feedback_label['text'] = \
                    "Missing input for '{}'".format(k)
                return

        app_lists = dict()

        for child in self.services_table.get_children():
            values = self.services_table.item(child)["values"]
            if not app_lists.get(values[1]):
                app_lists[values[1]] = {'_apps': list(), 'apps': list()}

            # app_lists[values[1]].append(values[0])
            app_lists[values[1]]['_apps'].append(values[0])

        for child in self.app_env_table.get_children():
            if not app_lists.get('AppleEvents'):
                app_lists['AppleEvents'] = {'_apps': list(), 'apps': list()}

            app_lists['AppleEvents']['_apps'].append(
                ','.join(self.app_env_table.item(child)["values"])
            )

        if not any(app_lists.keys()):
            self._feedback_label['text'] = 'You must provide at least one ' \
                                           'payload type to create a profile!'
            return

        sign = self._payload_sign.get()

        desktop_path = os.path.expanduser('~/Desktop')
        filename = tkFileDialog.asksaveasfilename(
            parent=self,
            defaultextension='.mobileconfig',
            initialdir=desktop_path,
            initialfile='tccprofile.mobileconfig',
            title='Save TCC Profile...'
        )

        tcc_profile = PrivacyProfiles(
            payload_description=payload['Description'],
            payload_name=payload['Name'],
            payload_identifier=payload['Identifier'],
            payload_organization=payload['Organization'],
            profile_removal_password=None,
            sign_cert=None if sign == 'No' else sign,
            filename=filename,
            removal_date=None,
            timezone=None,
        )

        tcc_profile.set_services_dict(app_lists)
        tcc_profile.build_profile(allow=True)
        tcc_profile.write()

        self._feedback_label['text'] = ''

    def click_quit(self, event=None):
        print("The user clicked 'Quit'")
        self.master.destroy()

    @staticmethod
    def _list_signing_certs():
        output = subprocess.check_output(
            ['/usr/bin/security', 'find-identity', '-p', 'codesigning', '-v']
        ).split('\n')

        cert_list = ['No']
        for i in output:
            r = re.findall(r'"(.*?)"', i)
            if r:
                cert_list.extend(r)

        return cert_list

    def _app_picker(self, var_name):
        app_name = tkFileDialog.askopenfilename(
            parent=self,
            # filetypes=[('App', '.app')],
            initialdir='/Applications',
            title='Select App'
        )
        getattr(self, var_name).set(app_name)
        getattr(self, var_name + '_display').set(os.path.basename(app_name))

    def _add_apple_event(self):
        source_app = self._app_env_source_var.get()
        target_app = self._app_env_target_var.get()

        if not all([source_app, target_app]):
            print('Source and Target not both provided')
            return

        self.app_env_table.insert('', 'end', values=(source_app, target_app))
        self._app_env_target_var.set('')
        self._app_env_source_var.set('')
        self._app_env_source_var_display.set('')
        self._app_env_target_var_display.set('')

    def _add_service(self):
        target_app = self._services_target_var.get()
        selected_service = self._selected_service.get()
        allow_deny = 'Allow' if \
            self._available_services.get(selected_service) else 'Deny'

        if not target_app:
            print('Target app not provided')
            return

        self.services_table.insert(
            '', 'end',
            values=(target_app, selected_service, allow_deny)
        )
        self._services_target_var.set('')
        self._services_target_var_display.set('')

    def _remove_table_item(self, table):
        treeview_obj = getattr(self, table)
        selected_items = treeview_obj.selection()

        for item in selected_items:
            treeview_obj.delete(item)


def read_plist(filepath):
    """Read a .plist file from filepath. Return the unpacked root object (which is usually a dictionary)."""
    plistData = NSData.dataWithContentsOfFile_(filepath)
    dataObject, dummy_plistFormat, error = (
        NSPropertyListSerialization.
        propertyListFromData_mutabilityOption_format_errorDescription_(plistData, NSPropertyListMutableContainers, None, None))
    if dataObject is None:
        if error:
            error = error.encode('ascii', 'ignore')
        else:
            error = "Unknown error"
        errmsg = "%s in file %s" % (error, filepath)
        raise NSPropertyListSerializationException(errmsg)
    else:
        return dataObject


class PrivacyProfilesException(Exception):
    """Basic error handling for PrivacyProfiles()"""
    pass


class PrivacyProfiles(object):
    """Class for Privacy Profiles Creation"""
    # List of Payload types to iterate on because lazy code is good code
    PAYLOADS = [
        'AddressBook',
        'Calendar',
        'Reminders',
        'Photos',
        'Camera',
        'FileProviderPresence',
        'ListenEvent',
        'MediaLibrary',
        'Microphone',
        'Accessibility',
        'PostEvent',
        'ScreenCapture',
        'SpeechRecognition',
        'SystemPolicyAllFiles',
        'SystemPolicyDesktopFolder',
        'SystemPolicyDocumentsFolder',
        'SystemPolicyDownloadsFolder',
        'SystemPolicyRemovableVolumes',
        'SystemPolicyNetworkVolumes',
        'SystemPolicySysAdminFiles',
        'AppleEvents'
    ]

    DENY_PAYLOADS = [
        'Camera',
        'ListenEvent',
        'Microphone',
        'ScreenCapture'
    ]

    def __init__(self, payload_description, payload_name, payload_identifier,
                 payload_organization, profile_removal_password,
                 sign_cert, filename, removal_date, timezone):
        """Creates a Privacy Preferences Policy Control Profile for macOS Mojave."""
        # Init the things to put in the template, and elsewhere
        self.payload_description = payload_description
        self.payload_name = payload_name
        self.payload_identifier = payload_identifier
        self.payload_organization = payload_organization
        self.payload_type = 'com.apple.TCC.configuration-profile-policy'
        self.payload_uuid = str(uuid.uuid1()).upper()  # This is used in the 'PayloadContent' part of the profile
        self.profile_uuid = str(uuid.uuid1()).upper()  # This is used in the root of the profile
        self.payload_version = 1  # According to Apple documentation, this value must be `1`.
        # The payload_version argument will be soft deprecated for the time being.

        # Profile removal details. Only add the 'RemovalPassword' entry to 'PayloadContent' if there is one.
        if profile_removal_password:
            self.profile_removable = True
            self.profile_removal_password = profile_removal_password
        else:
            self.profile_removal_password = False
            self.profile_removable = False

        # Basic requirements for this profile to work
        self.template = {
            'PayloadContent': [
                {
                    'PayloadDescription': self.payload_description,
                    'PayloadDisplayName': self.payload_name,
                    'PayloadIdentifier': '{}.{}'.format(self.payload_identifier, self.payload_uuid),  # This needs to be different to the root 'PayloadIdentifier'
                    'PayloadOrganization': self.payload_organization,
                    'PayloadType': self.payload_type,
                    'PayloadUUID': self.payload_uuid,
                    'PayloadVersion': self.payload_version,
                    'Services': dict()  # This will be an empty list to house the dicts.
                }
            ],
            'PayloadDescription': self.payload_description,
            'PayloadDisplayName': self.payload_name,
            'PayloadIdentifier': self.payload_identifier,
            'PayloadOrganization': self.payload_organization,
            'PayloadScope': 'system',  # What's the point in making this a user profile?
            'PayloadType': 'Configuration',
            'PayloadUUID': self.profile_uuid,
            'PayloadVersion': self.payload_version,
            'PayloadRemovalDisallowed': self.profile_removable,  # Boolean. Requires password to delete if value is True; False value allows removal.
        }

        # Only add removal password if provided. This is recorded in plain text. Sign profile before deploying.
        self.profile_removal_password = self._set_profile_removal_password(profile_removal_password)

        if self.profile_removable:
            self.template['PayloadContent'][0]['RemovalPassword'] = self.profile_removal_password

        # If a removal date is specified
        self.removal_date = self._set_profile_removal_date(removal_date)
        self.timezone = self._set_timezone(timezone)

        if self.removal_date and self.timezone:
            self.template['RemovalDate'] = self._utc_formatted_time(local_time=self.removal_date, timezone=self.timezone)
        elif self.removal_date and not self.timezone:
            print 'A time zone for the target Mac must be provided when specifying a removal date. For example: --timezone="Australia/Brisbane"'
            print 'The time zone of the target is used as the time zone on the profile build machine may differ.'
            sys.exit(1)

        self._app_lists = dict()
        self._sign_cert = self._set_sign_profile(sign_cert)
        self._filename = self._set_filename(filename)

    @staticmethod
    def _utc_formatted_time(local_time, timezone):
        """Returns a UTC date for use where a date is required in UTC format"""
        valid_time_format = '%Y-%m-%d %H:%M'

        try:
            timezone = pytz.timezone(timezone)
            local_time = datetime.datetime.strptime(local_time, valid_time_format)
            # Don't guess about DST. By setting is_dst=None, any ambigious time, or a time that does not
            # exist because skip forward/backward in DST change over, an exception will be raised.
            try:
                local_time = timezone.localize(local_time, is_dst=None)
            except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError), e:
                # If an AmbiguousTimeError occurs, it is likely because that time has occurred more than once.
                # For example, 2002-10-27 01:30 happened twice in the US/Eastern timezone when DST ended.
                # If a NonExistentTimeError occurs, it is because that particular point in time has not/does not occur.
                # For example, 2018-10-07 02:30 does not occur in Australia/Sydney because DST starts at 02:00 with clocks
                # skipping forward straight to 03:00
                raise e

            utc_time = local_time.astimezone(pytz.utc)

            return utc_time

        except Exception:
            raise

    @staticmethod
    def _is_accessible(path):
        """Returns if the path is accessible to the current user running this utility. Exits with error if not readable."""
        if os.access(path, os.R_OK):  # Only need to determine if read access is possible
            return True
        else:
            raise PrivacyProfilesException(errno.EACCES, 'Permission denied accessing {}'.format(path))

    def set_services_dict(self, args):
        if not isinstance(args, dict):
            arguments = vars(args)
            app_lists = dict()
            # apple_events_apps = arguments.get('events_apps_list', False)

            # Make sure AppleEvents apps are splitabble
            if arguments.get('events_apps_list', False) is not None and not all([len(app.split(',')) == 2 for app in arguments.get('events_apps_list', False)]):
                print 'AppleEvents applications must be in the format of /Application/Path/EventSending.app,/Application/Path/EventReceiving.app'
                print 'or'
                print ('/Volumes/ExtDisk/Path/EventSending.app:/Application/OverridePath/EventSending.app,'
                       '/Volumes/ExtDisk/Path/EventReceiving.app:/Application/OverridePath/EventReceiving.app')
                sys.exit(1)

            # Build up args to pass to the class init
            app_lists['Accessibility'] = {'_apps': arguments.get('accessibility_apps_list', False), 'apps': list()}
            app_lists['AddressBook'] = {'_apps': arguments.get('address_book_apps_list', False), 'apps': list()}
            app_lists['AppleEvents'] = {'_apps': arguments.get('events_apps_list', False), 'apps': list()}
            app_lists['Calendar'] = {'_apps': arguments.get('calendar_apps_list', False), 'apps': list()}
            app_lists['Camera'] = {'_apps': arguments.get('camera_apps_list', False), 'apps': list()}
            app_lists['FileProviderPresence'] = {'_apps': arguments.get('file_providers_apps_list', False), 'apps': list()}
            app_lists['ListenEvent'] = {'_apps': arguments.get('listen_event_apps_list', False), 'apps': list()}
            app_lists['MediaLibrary'] = {'_apps': arguments.get('media_library_apps_list', False), 'apps': list()}
            app_lists['Microphone'] = {'_apps': arguments.get('microphone_apps_list', False), 'apps': list()}
            app_lists['Photos'] = {'_apps': arguments.get('photos_apps_list', False), 'apps': list()}
            app_lists['PostEvent'] = {'_apps': arguments.get('post_event_apps_list', False), 'apps': list()}
            app_lists['Reminders'] = {'_apps': arguments.get('reminders_apps_list', False), 'apps': list()}
            app_lists['ScreenCapture'] = {'_apps': arguments.get('screen_capture_apps_list', False), 'apps': list()}
            app_lists['SpeechRecognition'] = {'_apps': arguments.get('speech_recognition_apps_list', False), 'apps': list()}
            app_lists['SystemPolicyAllFiles'] = {'_apps': arguments.get('allfiles_apps_list', False), 'apps': list()}
            app_lists['SystemPolicyDesktopFolder'] = {'_apps': arguments.get('desktop_apps_list', False), 'apps': list()}
            app_lists['SystemPolicyDocumentsFolder'] = {'_apps': arguments.get('documents_apps_list', False), 'apps': list()}
            app_lists['SystemPolicyDownloadsFolder'] = {'_apps': arguments.get('downloads_apps_list', False), 'apps': list()}
            app_lists['SystemPolicyRemovableVolumes'] = {'_apps': arguments.get('removable_volumes_apps_list', False), 'apps': list()}
            app_lists['SystemPolicyNetworkVolumes'] = {'_apps': arguments.get('network_volumes_apps_list', False), 'apps': list()}
            app_lists['SystemPolicySysAdminFiles'] = {'_apps': arguments.get('sysadmin_apps_list', False), 'apps': list()}
        else:
            app_lists = args

        for key in app_lists.keys():
            if app_lists[key]['_apps'] is not None:
                for app in app_lists[key]['_apps']:
                    value = dict()
                    sending_app = app.split(',')[0]
                    receiving_app = app.split(',')[1] if ',' in app else False

                    value['sending_app_path'] = sending_app.split(':')[0] if ':' in sending_app else sending_app
                    value['sending_app_path_override'] = app.split(':')[1] if ':' in app else False

                    if key == 'AppleEvents' and app.count(',') == 1:
                        receiving_app = app.split(',')[1]
                        if sending_app.count(':') > 1 or receiving_app.count(':') > 1:
                            print 'Too many \':\' characters in AppleEvents app string. One \':\' per sender and recever app is excpected.'
                            sys.exit(1)
                        else:
                            value['sending_app_path'] = sending_app.split(':')[0] if ':' in sending_app else value['sending_app_path']
                            value['sending_app_path_override'] = sending_app.split(':')[1] if ':' in sending_app else False
                            if receiving_app:
                                value['receiving_app_path'] = receiving_app.split(':')[0]
                                value['receiving_app_path_override'] = receiving_app.split(':')[1] if ':' in receiving_app else False
                    if value not in app_lists[key]['apps']:
                        app_lists[key]['apps'].append(value)

        # Remove all None values in dict
        for key in app_lists.keys():
            if app_lists[key]['_apps'] is None:
                del app_lists[key]
            else:
                # Get rid of the _apps as it's no longer required
                app_lists[key] = app_lists[key]['apps']

        # Handle if no payload arguments are supplied,
        # Can't create an empty profile.
        if not any(app_lists.keys()):
            print 'You must provide at least one payload type to create a profile.'
            raise TCCProfileException

        self._app_lists = app_lists

        # Create payload lists in the services_dict
        for payload in self.PAYLOADS:
            if app_lists.get(payload):
                self.template['PayloadContent'][0]['Services'][payload] = []

    @staticmethod
    def _app_name(app_obj):
        return os.path.basename(os.path.splitext(app_obj)[0])

    def build_profile(self, allow):
        """Builds the profile out into the full dict required to write as a plist or to stdout."""
        for payload in self.PAYLOADS:
            if self._app_lists.get(payload):
                for app in self._app_lists[payload]:
                    # Common payload values
                    sending_app = dict()
                    sending_app['path'] = app['sending_app_path']
                    sending_app['path_override'] = app.get('sending_app_path_override', False)
                    sending_app['codesign_result'] = self._get_code_sign_requirements(path=sending_app['path'])
                    sending_app['app_name'] = self._app_name(app_obj=sending_app['path'])

                    app_identifier_type = self._get_identifier_and_type(app_path=sending_app['path'], override_path=sending_app['path_override'])
                    sending_app['identifier'] = app_identifier_type['identifier']
                    sending_app['identifier_type'] = app_identifier_type['identifier_type']

                    # For any payload that can only be set to 'Deny', change settings to enforce.
                    if payload in self.DENY_PAYLOADS or not allow:
                        _allow = False
                        allow_statement = 'Deny'
                    else:
                        _allow = allow
                        allow_statement = 'Allow'

                    # Add details about the receiving app if the payload is an AppleEvents type
                    if payload == 'AppleEvents':
                        receiving_app = dict()
                        receiving_app['path'] = app.get('receiving_app_path', False)
                        receiving_app['path_override'] = app.get('receiving_app_path_override', False)
                        receiving_app['codesign_result'] = self._get_code_sign_requirements(path=receiving_app['path'])
                        receiving_app['app_name'] = self._app_name(app_obj=receiving_app['path'])
                        app_identifier_type = self._get_identifier_and_type(app_path=receiving_app['path'], override_path=receiving_app['path_override'])
                        receiving_app['identifier'] = app_identifier_type['identifier']
                        receiving_app['identifier_type'] = app_identifier_type['identifier_type']
                        comment = '{} {} to send {} control to {}'.format(allow_statement, sending_app['app_name'], payload, receiving_app['app_name'])
                    else:
                        receiving_app = False
                        comment = '{} {} control for {}'.format(allow_statement, payload, sending_app['app_name'])

                    # Pass the payload over to the _build_payload function
                    payload_dict = self._build_payload(
                        sending_app=sending_app,
                        receiving_app=receiving_app,
                        allowed=_allow,
                        apple_event=True if payload == 'AppleEvents' else False,
                        comment=comment,
                    )

                    # Add the assembled payload_dict to the template
                    if payload_dict not in self.template['PayloadContent'][0]['Services'][payload]:
                        self.template['PayloadContent'][0]['Services'][payload].append(payload_dict)

    def _build_payload(self, sending_app, receiving_app, allowed, apple_event, comment):
        """Builds an Accessibility payload for the profile."""
        if isinstance(sending_app, dict) and isinstance(apple_event, bool) and isinstance(comment, str):
            # Only return a basic dict, even though the Services needs a dict
            # supplied, and the 'Accessibility' "payload" is a list of dicts.
            result = {
                'Allowed': allowed,
                'CodeRequirement': sending_app['codesign_result'],
                'Comment': comment,
                'Identifier': sending_app['identifier'],
                'IdentifierType': sending_app['identifier_type'],
            }

            # If the payload is an AppleEvent type, there are additional
            # requirements relating to the receiving app.
            if apple_event and isinstance(receiving_app, dict):
                result['AEReceiverIdentifier'] = receiving_app['identifier']
                result['AEReceiverIdentifierType'] = receiving_app['identifier_type']
                result['AEReceiverCodeRequirement'] = receiving_app['codesign_result']

            return result

    def write(self):
        """Handles writing the profile out to file, and will also create the configuration template if the relevant argument is provided."""
        # Write out the file if a filename is provided, otherwise dump to stdout
        if self._filename:
            # Write the plist out to file
            plistlib.writePlist(self.template, self._filename)

            # Sign it if required
            if self._sign_cert:
                self._sign_profile(certificate_name=self._sign_cert, input_file=self._filename)
        else:
            # Print as formatted plist out to stdout
            print plistlib.writePlistToString(self.template).rstrip('\n')

    @staticmethod
    def _set_timezone(timezone):
        if timezone and len(timezone):
            return timezone[0]
        else:
            return False

    @staticmethod
    def _set_profile_removal_date(removal_date):
        if removal_date and len(removal_date):
            return removal_date[0]
        else:
            return False

    @staticmethod
    def _set_profile_removal_password(profile_removal_password):
        if profile_removal_password and len(profile_removal_password):
            return profile_removal_password[0]
        else:
            return False

    @staticmethod
    def _set_sign_profile(sign_cert):
        if sign_cert and len(sign_cert):
            return sign_cert[0]
        else:
            return False

    @staticmethod
    def _set_filename(filename):
        if filename:
            _filename = os.path.expandvars(os.path.expanduser(filename))
            if not os.path.splitext(filename)[1] == '.mobileconfig':
                _filename = filename.replace(os.path.splitext(filename)[1], '.mobileconfig')

            return _filename
        else:
            return None

    @staticmethod
    def _get_file_mime_type(path):
        """Returns the mimetype of a given file."""
        if os.path.exists(path.rstrip('/')):
            cmd = ['/usr/bin/file', '--mime-type', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                # Only need the mime type, so return the last bit
                result = result.replace(' ', '').replace('\n', '').split(':')[1].split('/')[1]
                return result

    @staticmethod
    def _read_shebang(app_path):
        """Returns the contents of the shebang in a script file, as long as env is not in the shebang."""
        with open(app_path, 'r') as textfile:
            line = textfile.readline().rstrip('\n')
            if line.startswith('#!') and 'env ' not in line:
                return line.replace('#!', '')
            elif line.startswith('#!') and 'env ' in line:
                raise Exception('Cannot check codesign for shebangs that refer to \'env\'.')

    def _get_code_sign_requirements(self, path):
        """Returns the values for the CodeRequirement key."""
        def _is_code_signed(path):
            """Returns True/False if specified path is code signed or not."""
            cmd = ['/usr/bin/codesign', '-dr', '-', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                return True
            elif process.returncode is 1 and 'not signed' in error:
                return False

        # Make sure the path exists and is readable.
        if os.path.exists(path.rstrip('/')) and self._is_accessible(path.rstrip('/')):
            # Handle situations where path is a script, and shebang is
            # ['/bin/sh', '/bin/bash', '/usr/bin/python']
            mimetype = self._get_file_mime_type(path=path)

            if mimetype in ['x-python', 'x-shellscript']:
                if not _is_code_signed(path):  # Only use shebang path if a script is not code signed
                    path = self._read_shebang(app_path=path)

            cmd = ['/usr/bin/codesign', '-dr', '-', path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result, error = process.communicate()

            if process.returncode is 0:
                # For some reason, part of the output gets dumped to stderr, but the bit we need goes to stdout
                # Also, there can be multiple lines in the result, so handle this properly
                # There are circumstances where the codesign 'designated => ' is not the start of the line, so handle these.
                result = result.rstrip('\n').splitlines()
                result = [line for line in result if 'designated => ' in line][0]
                result = result.partition('designated => ')
                result = result[result.index('designated => ') + 1:][0]
                # result = [x.rstrip('\n') for x in result.splitlines() if x.startswith('designated => ')][0]
                return result
            elif process.returncode is 1 and 'not signed' in error:
                print 'App at {} is not signed. Exiting.'.format(path)
                sys.exit(1)
        else:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    def _get_identifier_and_type(self, app_path, override_path=False):
        """Checks file type, and returns appropriate values for `Identifier`and `IdentifierType` keys in the final profile payload."""
        # Only change the app_path to the override path if '.app' is not the file extension, because app's should have CFBundleIdentifier payload
        # in the App/Contents/Info.plist file
        if override_path and os.path.splitext(override_path)[1] != '.app' and os.path.splitext(app_path)[1] != '.app':
            app_path = override_path.rstrip('/') if override_path else app_path.rstrip('/')

        # Determine mimetype
        mimetype = self._get_file_mime_type(path=app_path)

        # Check for mimetype of file
        if mimetype in ['x-shellscript', 'x-python']:
            identifier = app_path
            identifier_type = 'path'
        else:
            try:
                identifier = read_plist(os.path.join(app_path.rstrip('/'), 'Contents/Info.plist'))['CFBundleIdentifier']
                identifier_type = 'bundleID'
            except Exception:
                identifier = app_path
                identifier_type = 'path'

        return {'identifier': identifier, 'identifier_type': identifier_type}

    def _sign_profile(self, certificate_name, input_file):
        """Signs the profile."""
        if self._sign_cert and os.path.exists(input_file) and input_file.endswith('.mobileconfig'):
            cmd = ['/usr/bin/security', 'cms', '-S', '-N', certificate_name, '-i', input_file, '-o', '{}'.format(input_file.replace('.mobileconfig', '_Signed.mobileconfig'))]
            subprocess.call(cmd)


class SaneUsageFormat(argparse.HelpFormatter):
    """Makes the help output somewhat more sane. Code used was from Matt Wilkie.
    http://stackoverflow.com/questions/9642692/argparse-help-without-duplicate-allcaps/9643162#9643162
    """

    def _format_action_invocation(self, action):
        if not action.option_strings:
            default = self._get_default_metavar_for_positional(action)
            metavar, = self._metavar_formatter(action, default)(1)
            return metavar
        else:
            parts = []
            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)
            # if the Optional takes a value, format is:
            #    -s ARGS, --long ARGS
            else:
                default = self._get_default_metavar_for_optional(action)
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    parts.append(option_string)
                return '{} {}'.format(', '.join(parts), args_string)
            return ', '.join(parts)

    def _get_default_metavar_for_optional(self, action):
        return action.dest.upper()


def parse_args():
    parser = argparse.ArgumentParser(formatter_class=SaneUsageFormat)

    parser.add_argument(
        '--ab', '--address-book',
        type=str,
        nargs='*',
        dest='address_book_apps_list',
        metavar='<app paths>',
        help='Generate an AddressBook payload for the specified applications,',
        required=False,
    )

    parser.add_argument(
        '--cal', '--calendar',
        type=str,
        nargs='*',
        dest='calendar_apps_list',
        metavar='<app paths>',
        help='Generate a Calendar payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--rem', '--reminders',
        type=str,
        nargs='*',
        dest='reminders_apps_list',
        metavar='<app paths>',
        help='Generate a Reminders payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--pho', '--photos',
        type=str,
        nargs='*',
        dest='photos_apps_list',
        metavar='<app paths>',
        help='Generate a Photos payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--cam', '--camera',
        type=str,
        nargs='*',
        dest='camera_apps_list',
        metavar='<app paths>',
        help='Generate a Camera payload for the specified applications. '
             'This will be a DENY payload.',
        required=False,
    )

    parser.add_argument(
        '--lis', '--listenevents',
        type=str,
        nargs='*',
        dest='listen_event_apps_list',
        metavar='<app paths>',
        help='Generate a ListenEvent payload for the specified applications. '
             'This will be a DENY payload.',
        required=False,
    )

    parser.add_argument(
        '--screen', '--screencapture',
        type=str,
        nargs='*',
        dest='screen_capture_apps_list',
        metavar='<app paths>',
        help='Generate a ScreenCapture payload for the specified applications. '
             'This will be a DENY payload.',
        required=False,
    )

    parser.add_argument(
        '--mic', '--microphone',
        type=str,
        nargs='*',
        dest='microphone_apps_list',
        metavar='<app paths>',
        help='Generate a Microphone payload for the specified applications. '
             'This will be a DENY payload.',
        required=False,
    )

    parser.add_argument(
        '--acc', '--accessibility',
        type=str,
        nargs='*',
        dest='accessibility_apps_list',
        metavar='<app paths>',
        help='Generate an Accessibility payload for the specified applications.',
        required=False,
    )

    parser.add_argument(
        '--pe', '--post-event',
        type=str,
        nargs='*',
        dest='post_event_apps_list',
        metavar='<app paths>',
        help='Generate a PostEvent payload for the specified applications to '
             'allow CoreGraphics APIs to send CGEvents.',
        required=False,
    )

    parser.add_argument(
        '--af', '--allfiles',
        type=str,
        nargs='*',
        dest='allfiles_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyAllFiles payload for the specified '
             'applications. This applies to all protected system files.',
        required=False,
    )

    parser.add_argument(
        '--file', '--fileprovider',
        type=str,
        nargs='*',
        dest='file_providers_apps_list',
        metavar='<app paths>',
        help='Generate an FileProviderPresence payload for the specified '
             'applications. This applies to File Provider Presence.',
        required=False,
    )

    parser.add_argument(
        '--media', '--medialibrary',
        type=str,
        nargs='*',
        dest='media_library_apps_list',
        metavar='<app paths>',
        help='Generate a MediaLibrary payload for the specified '
             'applications. This applies to Media Library.',
        required=False,
    )

    parser.add_argument(
        '--speech', '--speechrecognition',
        type=str,
        nargs='*',
        dest='speech_recognition_apps_list',
        metavar='<app paths>',
        help='Generate a SpeechRecognition payload for the specified '
             'applications. This applies to Speech Recognition.',
        required=False,
    )

    parser.add_argument(
        '--desk', '--desktopfolder',
        type=str,
        nargs='*',
        dest='desktop_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyDesktopFolder payload for the specified '
             'applications. This applies to the Desktop folder.',
        required=False,
    )

    parser.add_argument(
        '--doc', '--documentsfolder',
        type=str,
        nargs='*',
        dest='documents_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyDocumentsFolder payload for the specified '
             'applications. This applies to the Ddocuments folder.',
        required=False,
    )

    parser.add_argument(
        '--down', '--downloadsfolder',
        type=str,
        nargs='*',
        dest='downloads_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyDownloadsFolder payload for the specified '
             'applications. This applies to the Downloads folder.',
        required=False,
    )

    parser.add_argument(
        '--rvol', '--removablevolumes',
        type=str,
        nargs='*',
        dest='removable_volumes_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyRemovableVolumes payload for the specified '
             'applications. This applies to removable volumes.',
        required=False,
    )

    parser.add_argument(
        '--nvol', '--networkvolumes',
        type=str,
        nargs='*',
        dest='network_volumes_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicyNetworkVolumes payload for the specified '
             'applications. This applies to network volumes.',
        required=False,
    )

    parser.add_argument(
        '--ae', '--apple-event',
        type=str,
        nargs='*',
        dest='events_apps_list',
        metavar='<app paths>',
        help='Generate an AppleEvents payload for the specified applications. '
             'This allows applications to send restricted AppleEvents to '
             'another process',
        required=False,
    )

    parser.add_argument(
        '--sf', '--sysadminfiles',
        type=str,
        nargs='*',
        dest='sysadmin_apps_list',
        metavar='<app paths>',
        help='Generate an SystemPolicySysAdminFiles payload for the specified '
             'applications.This applies to some files used in system '
             'administration.',
        required=False,
    )

    parser.add_argument(
        '--allow',
        action='store_true',
        dest='allow_app',
        default=False,
        help='Configure the profile to allow control for all apps provided '
             'with the --apps command.',
        required=False
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        dest='payload_filename',
        metavar='payload_filename',
        help='Filename to save the profile as.',
        required=False,
    )

    parser.add_argument(
        '--pd', '--payload-description',
        type=str,
        dest='payload_description',
        metavar='payload_description',
        help='A short and sweet description of the payload.',
        required=True,
    )

    parser.add_argument(
        '--pi', '--payload-identifier',
        type=str,
        dest='payload_identifier',
        metavar='payload_identifier',
        help='An identifier to use for the profile. Example: org.foo.bar',
        required=True,
    )

    parser.add_argument(
        '--pn', '--payload-name',
        type=str,
        dest='payload_name',
        metavar='payload_name',
        help='A short and sweet name for the payload.',
        required=True,
    )

    parser.add_argument(
        '--po', '--payload-org',
        type=str,
        dest='payload_org',
        metavar='payload_org',
        help='Organization to use for the profile.',
        required=True,
    )

    parser.add_argument(
        '--removable',
        type=str,
        nargs=1,
        dest='profile_removal_password',
        metavar='<password>',
        help='Sets the profile to only be removable if the password provided '
        'is used to remove it.',
        required=False,
    )

    parser.add_argument(
        '-s', '--sign',
        type=str,
        nargs=1,
        dest='sign_profile',
        metavar='certificate_name',
        help='Signs a profile using the specified Certificate Name. To list '
             'code signing certificate names: /usr/bin/security find-identity '
             '-p codesigning -v',
        required=False,
    )

    parser.add_argument(
        '--removal-date',
        type=str,
        nargs=1,
        dest='profile_removal_date',
        metavar='"YYYY-mm-dd HH:MM"',
        help='The date and time on which this profile will automatically '
             'be removed. Must be in YYYY-mm-dd HH:MM format. '
             'Example: "2018-09-29 14:30"',
        required=False,
    )

    parser.add_argument(
        '--tz', '--timezone',
        type=str,
        nargs=1,
        dest='timezone',
        metavar='"Country/City"',
        help='The timezone of the destination system receiving this profile.'
             'In the format of "Country/City". Example: "Australia/Brisbane"',
        required=False,
    )

    parser.add_argument(
        '-v', '--version',
        action='version',
        version=VERSION_STRING
    )

    # parser.add_argument(
    #     '--lg', '--launch-gui',
    #     action='store_true',
    #     default=False,
    #     dest='launch_gui',
    #     help='Launch the GUI and populate the provided values passed via the '
    #          'arguments.',
    #     required=False
    # )

    return parser.parse_args()


def launch_gui(args=None):
    info = AppKit.NSBundle.mainBundle().infoDictionary()
    info['LSUIElement'] = True

    root = tk.Tk()
    app = App(root)
    AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    app.mainloop()


def main():
    if len(sys.argv) == 1:
        launch_gui()
        sys.exit(0)
    else:
        args = parse_args()

        # if args.launch_gui:
        #     launch_gui(args)

    tcc_profile = PrivacyProfiles(
        payload_description=args.payload_description,
        payload_name=args.payload_name,
        payload_identifier=args.payload_identifier,
        payload_organization=args.payload_org,
        profile_removal_password=args.profile_removal_password,
        sign_cert=args.sign_profile,
        filename=args.payload_filename,
        removal_date=args.profile_removal_date,
        timezone=args.timezone,
    )

    # Insert the service dict into the template
    tcc_profile.set_services_dict(args)

    # Iterate over the payloads dict to build payloads
    tcc_profile.build_profile(allow=args.allow_app)

    tcc_profile.write()


if __name__ == '__main__':
    main()
