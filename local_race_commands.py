#!/usr/bin/python

import requests
import ConfigParser
from flask import Flask, request
import sqlite3
import bs4
import sys
import datetime
import time


def web_hook():
    data = {'name': 'Manual', 'text': sys.argv[1]}
    called = ''

    config = ConfigParser.RawConfigParser()
    config.read('./config.ini')

    # make sure I didn't send the message
    if data['name'] != config.get('GroupMe', 'bot_name'):
        message = data['text'].split(' ')
        if message[0].lower() == '!bot':
            # You have asked the bot to do something. Now do what it asks.
            if len(message) > 1:
                if message[1].lower() == 'add':
                    called = 'add'
                    if len(message) == 4:
                        add_race_watch(message[2], message[3])
                    elif len(message) == 3:
                        add_race_watch(message[2], '24')
                    elif len(message) < 3:
                        missing_info()

                elif message[1].lower() == 'remove' or message[1].lower() == 'delete':
                    called = 'remove/delete'
                    if len(message) < 3:
                        missing_info()
                    else:
                        remove_race_watch(message[2])

                elif message[1].lower() == 'update':
                    called = 'update'
                    if len(message) < 4:
                        missing_info()
                    else:
                        update_race_watch(message[2], message[3])

                elif message[1].lower() == 'list':
                    called = 'list'
                    list_race_watch()

                elif message[1].lower() == 'status':
                    called = 'status'
                    if len(message) < 3:
                        missing_info()
                    else:
                        get_pilot_count(message[2])

                else:
                    called = 'help'
                    help_info()
            else:
                called = 'Error Help'
                help_info()

    return called, 200


def missing_info():
    body = "Missing required parameter."
    send_message(body)
    help_info()


def help_info():
    # This will send a message with what I can do.
    message = '!bot help --\n' \
              'I can do the following things.\n\n' \
              '!bot add <raceID> <maxPilots> -- Add a race to the auto close Notify list. Defaults to 24 pilots ' \
              'if none specified\n\n' \
              '!bot update <raceID> <maxPilots> -- Updates the specified race\'s maxPilots\n\n' \
              '!bot remove OR delete <raceID> -- Removes the specified race from the watch list.\n\n' \
              '!bot list -- Lists all races currently being watched by me.\n\n' \
              '!bot status <raceID> -- Gets the current pilot count for specified race.'

    print(message)


def get_pilot_count(raceID):
    # Get the current pilot count for raceID
    conn, c = get_db_conn()
    c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
    r_data = c.fetchone()

    if r_data:
        body = 'Race {} currently has {} pilots, with a max of {}.'.format(r_data[0], r_data[3], r_data[1])
        send_message(body)
    else:
        body = 'I am not currently watching Race {}.\n' \
               'This could be because it has reached it\'s limit and I stopped watching.\n' \
               'Or I wasn\'t watching it.'
        send_message(body)


def list_race_watch():
    # list all races currently being watched.
    conn, c = get_db_conn()
    c.execute('''SELECT * FROM races''')
    races = c.fetchall()

    if races:
        m_body = 'Currently Watching:\n' \
                 '---------\n'
        for race in races:
            current_status = race[6]
            if current_status:
                current_status = "Closed"
            elif current_status is None:
                current_status = "Unknown"
            elif not current_status:
                current_status = "Open"

            if not race[4]:
                title = "Not Retrieved Yet."
            else:
                title = unicode(race[4]).encode('utf-8')

            m_body += 'RaceId: {}\n' \
                      'Name: {}\n' \
                      'Max Pilots: {}, Current: {}.\n' \
                      'Current Status: {}\n' \
                      'Url: {}\n' \
                      '---------\n'.format(race[0], title, race[1], race[3], current_status, race[7])

        print(m_body)
    else:
        body = 'I am not currently watching any Races.'
        send_message(body)
    conn.close()


def update_race_watch(raceID, max_pilots):
    # This will update a race already being watched.
    body = "Updating Race {} to Max Pilots {}.".format(raceID, max_pilots)
    send_message(body)

    conn, c = get_db_conn()
    c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
    pre_check = c.fetchone()
    if pre_check:
        if pre_check[1] != int(max_pilots):
            c.execute('''UPDATE races SET max_pilots=? WHERE raceID=?''', (max_pilots, raceID))
            conn.commit()
            c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
            validate = c.fetchone()
            if validate:
                body = "Updated Race {} to Max Pilots of {}.".format(validate[0], validate[1])
                send_message(body)
        else:
            body = "No changes made. Already watching for Max Pilots of {} for Race {}".format(max_pilots, raceID)
            send_message(body)
    else:
        body = 'Race {} doesn\'t exist...\n' \
               'Going to add it for you.'.format(raceID)
        send_message(body)
        add_race_watch(raceID, max_pilots)

    conn.close()


def get_date_time(soup, conn, c, raceID):
    # Digging out the Date/Time

    # Digging out the date
    raw_date = soup.find(itemprop="startDate").getText()
    raw_time = soup.select_one('.text-center small').getText()
    raw_time = raw_time.split()
    date_time = "{} {} {}".format(raw_date, raw_time[1], raw_time[2])
    date_time = datetime.datetime.strptime(date_time, '%b %d, %Y %I:%M %p')

    if time.localtime().tm_isdst:
        date_time = date_time - datetime.timedelta(hours=-6)
        # -6
    else:
        date_time = date_time - datetime.timedelta(hours=-7)
        # -7

    c.execute('''UPDATE races SET date=? WHERE raceID=?''', (date_time, raceID))
    conn.commit()


def add_race_watch(raceID, max_pilots):
    # This will add a race to the watch list.
    config = ConfigParser.RawConfigParser()
    config.read('./config.ini')
    url = "{}{}{}/".format(config.get('multiGP', 'url'), config.get('multiGP', 'fancy_view_uri'), raceID)
    body = "Adding Race {} to watch list.".format(raceID)
    send_message(body)
    conn, c = get_db_conn()
    c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
    i_check = c.fetchone()
    if i_check:
        body = 'Already watching RaceID {} with a Max Pilots of {}.\n' \
               'I am going to check to see if it needs updated.'.format(i_check[0], i_check[1])
        send_message(body)
        update_race_watch(raceID, max_pilots)
    else:
        c.execute('''INSERT INTO races (raceID, max_pilots, notified, c_count, url) VALUES(?,?,?,?,?)''',
                  (raceID, max_pilots, False, 0, url))
        conn.commit()
        c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
        validate = c.fetchone()
        if validate:
            initial_data_grab(raceID, c, conn)
            c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
            current = c.fetchone()
            body = "Added RaceID {} with a Max Pilots of {}.\n" \
                   "Race currently has {} pilots signed up.\n" \
                   "Race URL: {}".format(current[0], current[1], current[3], url)
            send_message(body)

    conn.close()


def remove_race_watch(raceID):
    # This will remove a race from the watch list.
    body = 'Removing Race {} from the watch list.'.format(raceID)
    send_message(body)

    conn, c = get_db_conn()
    c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
    i_check = c.fetchone()
    if i_check:
        c.execute('''DELETE FROM races WHERE raceID=?''', (raceID,))
        conn.commit()
        c.execute('''SELECT * FROM races WHERE raceID=?''', (raceID,))
        validate = c.fetchone()
        if not validate:
            body = "I have stopped watching Race {}.".format(raceID)
            send_message(body)
    else:
        body = "I was not watching Race {}".format(raceID)
        send_message(body)

    conn.close()


def send_message(body):
    print(body)


def initial_data_grab(raceID, c, conn):
    headers = {'x-requested-with': 'XMLHttpRequest'}
    res = requests.get('https://www.multigp.com/mgp/races/view/{}/'.format(raceID), verify=False, headers=headers)
    soup = bs4.BeautifulSoup(res.text, "html.parser")
    count = len(soup.select('.block-white .row'))

    c.execute('''UPDATE races SET "c_count"=? WHERE raceID=?''', (count, raceID))
    conn.commit()

    get_date_time(soup, conn, c, raceID)


def get_db_conn():
    config = ConfigParser.RawConfigParser()
    config.read('./config.ini')
    db_path = config.get('database', 'auto_close')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    return conn, c


if __name__ == '__main__':
    web_hook()
