#!/usr/bin/env python3
# coding: UTF-8

import json
import pickle
import random
import re
import time
from collections import deque
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from cqsdk import CQBot, CQAt, RE_CQ_SPECIAL, RcvdPrivateMessage, \
    RcvdGroupMessage, SendGroupMessage, GroupMemberIncrease, GroupBan
from utils import match, reply


qqbot = CQBot(11235)
scheduler = BackgroundScheduler(
    timezone='Asia/Tokyo',
    job_defaults={'misfire_grace_time': 60},
    )


################
# Restriction
################
POI_GROUP = '378320628'
BANNED_MAX_DURATION = 1440
BANNED_RESET_TIME = timedelta(hours=20)
BAN_PATTERN = re.compile(r'\((\d+)\) *被管理员禁言')
UNBAN_PATTERN = re.compile(r'\((\d+)\) *被管理员解除禁言')

with open('admin.json', 'r', encoding="utf-8") as f:
    data = json.loads(f.read())
    ADMIN = data

with open('poi.json', 'r', encoding="utf-8") as f:
    data = json.loads(f.read())
    BANNED_WORDS = data.get("banned-words", [])
    IGNORED_WORDS = data.get("ignored-words", [])
    IGNORED_USERS = data.get("ignored-users", [])


class BanRecord:
    records = {}

    def __init__(self, count=0, last=datetime.utcnow()):
        self.count = count
        self.last = last

    def increase(self):
        self.count += 1
        self.last = datetime.now()

    @classmethod
    def get(cls, qq):
        if qq not in cls.records:
            cls.records[qq] = BanRecord()
        if datetime.utcnow() - cls.records[qq].last > BANNED_RESET_TIME:
            cls.records[qq] = BanRecord()
        return cls.records[qq]

    @classmethod
    def top(cls, n=10):
        # Refresh records
        for qq in cls.records.keys():
            cls.get(qq)
        # Sort records
        items = sorted(cls.records.items(),
                       key=lambda i: i[1].count,
                       reverse=True)
        return items[:n]


@qqbot.listener((RcvdGroupMessage, GroupMemberIncrease))
def restriction(message):
    if isinstance(message, (GroupMemberIncrease, )):
        return message.group != POI_GROUP
    if message.group != POI_GROUP:
        return True
    if message.qq in IGNORED_USERS:
        return True
    # else
    return False


@qqbot.listener((RcvdGroupMessage, ))
def words(message):
    lower_text = message.text.lower()
    # Ban
    if message.qq not in ADMIN:
        record = BanRecord.get(message.qq)
        for o in BANNED_WORDS:
            keywords = o.get('keywords', [])
            duration = o.get('duration', 10)
            if match(lower_text, keywords):
                duration *= 2 ** record.count
                duration = duration if duration > 0 else 1
                qqbot.send(GroupBan(message.group, message.qq, duration * 60))
                return True
    # Ignore
    if match(lower_text, IGNORED_WORDS):
        return True
    # else
    return False


@qqbot.listener((RcvdGroupMessage, ))
def banned(message):
    return  # Disabled for BAN event (TODO)
    if message.qq != '1000000':
        return
    m = BAN_PATTERN.search(message.text)
    if m is not None:
        qq = m.group(1)
        record = BanRecord.get(qq)
        record.increase()
        print("Banned: QQ {0} x {1}".format(qq, record.count))


@qqbot.listener((RcvdGroupMessage, RcvdPrivateMessage, ))
def bantop(message):
    if message.qq not in ADMIN:
        return
    texts = message.text.split()
    if not(len(texts) > 0 and texts[0] == '/bantop'):
        return
    try:
        n = int(texts[1])
    except:
        n = 4
    topN = BanRecord.top(n)
    texts = ["**** 禁言次数排名 ****"]
    for qq, record in topN:
        texts.append("{qq} {count}".format(
            qq=CQAt(qq), count=record.count))
    text = '\n'.join(texts)
    reply(qqbot, message, text)
    return True


################
# FAQ
################
FAQ_DEFAULT_INTERVAL = 60
FAQ = []


class FAQObject:
    def __init__(self, opts):
        self.keywords = opts["keywords"]
        self.whitelist = opts.get("whitelist", [])
        self.message = opts["message"]
        self.interval = opts.get("interval", FAQ_DEFAULT_INTERVAL)
        self.triggered = 0

with open('faq.json', 'r', encoding="utf-8") as f:
    jFAQ = json.loads(f.read())
    for jfaq in jFAQ:
        FAQ.append(FAQObject(jfaq))


@qqbot.listener((RcvdGroupMessage, ))
def faq(message):
    text = message.text.lower()
    now = time.time()
    for faq in FAQ:
        if not match(text, faq.keywords):
            continue
        if match(text, faq.whitelist):
            return True
        if (now - faq.triggered) < faq.interval:
            return True

        if isinstance(faq.message, list):
            send_text = random.choice(faq.message)
        else:
            send_text = faq.message

        faq.triggered = now
        reply(qqbot, message, send_text)
        return True


################
# roll
################
ROLL_LOWER = 2
ROLL_UPPER = 7000
ROLL_SEPARATOR = ','
ROLL_HELP = "[roll] 有效范围为 {} ~ {}".format(ROLL_LOWER, ROLL_UPPER)


@qqbot.listener((RcvdGroupMessage, ))
def roll(message):
    texts = message.text.split()
    if not (len(texts) > 0 and texts[0] == '/roll'):
        return
    texts = RE_CQ_SPECIAL.sub('', message.text).split()

    ranges = []
    for text in texts[1:6]:
        # /roll 100
        try:
            n = int(text)
            if ROLL_LOWER <= n <= ROLL_UPPER:
                ranges.append(n)
            else:
                reply(qqbot, message, ROLL_HELP)
                return True
            continue
        except:
            pass
        # /roll 1,20,100
        if ROLL_SEPARATOR in text:
            n = text.split(',')
            ranges.append(n)
            continue
        # else
        break
    if len(ranges) == 0:
        ranges = [100]

    rolls = []
    for n in ranges:
        if isinstance(n, int):
            rolls.append("{}/{}".format(random.randint(1, n), n))
        if isinstance(n, (list, tuple)):
            rolls.append("{}/{}".format(random.choice(n),
                                        ROLL_SEPARATOR.join(n)))
    roll_text = ", ".join(rolls)
    send_text = "[roll] [CQ:at,qq={}]: {}".format(message.qq, roll_text)

    reply(qqbot, message, send_text)
    return True


################
# repeat
################
REPEAT_QUEUE_SIZE = 32
REPEAT_COUNT_MIN = 2
REPEAT_COUNT_MAX = 4
queue = deque()


class QueueMessage:
    def __init__(self, text):
        self.text = text
        self.count = 0
        self.senders = set()
        self.repeated = False


class RandomQueue:
    queue = []

    @classmethod
    def next(cls):
        if len(cls.queue) == 0:
            cls.queue = 2 * [True, False, False]
            random.shuffle(cls.queue)
        return cls.queue.pop()


@qqbot.listener((RcvdGroupMessage, ))
def repeat(message):
    text = message.text
    sender = message.qq

    # Find & remove matched message from queue.
    msg = None
    for m in queue:
        if m.text == text:
            msg = m
            queue.remove(m)
            break

    # Increase message count
    if msg is None:
        msg = QueueMessage(text)
    msg.senders.add(sender)
    msg.count = len(msg.senders)

    # Push message back to queue
    queue.appendleft(msg)
    if len(queue) > REPEAT_QUEUE_SIZE:
        queue.pop()

    # Ban4 event
    if msg.repeated and sender not in ADMIN and RandomQueue.next():
        record = BanRecord.get(sender)
        duration = 2 ** record.count * 1
        duration = duration if duration > 0 else 1
        qqbot.send(GroupBan(message.group, sender, duration * 60))\

    # Repeat message
    if msg.repeated or msg.count < REPEAT_COUNT_MIN:
        return
    if random.randint(1, REPEAT_COUNT_MAX - msg.count + 1) == 1:
        reply(qqbot, message, msg.text)
        msg.repeated = True
        return True


################
# Join & Leave
################
@qqbot.listener((GroupMemberIncrease, ))
def join(message):
    qqbot.send(SendGroupMessage(
        group=message.group,
        text="{} 欢迎来到 poi 用户讨论群。新人请发女装照一张。".format(
            CQAt(message.operatedQQ))
    ))


# @qqbot.listener((GroupMemberDecrease, ))
# def leave(message):
#     qqbot.send(SendGroupMessage(
#         group=message.group,
#         text="{} 畏罪潜逃了".format(
#             CQAt(message.operatedQQ))
#     ))


################
# Persistence
################
PFILE = './persistence.txt'

try:
    with open(PFILE, 'rb') as f:
        BanRecord.records = pickle.load(f)
except FileNotFoundError:
    pass


@scheduler.scheduled_job('cron', minute='*')
def persistence():
    with open(PFILE, 'wb') as f:
        pickle.dump(BanRecord.records, f)


################
# __main__
################
if __name__ == '__main__':
    try:
        qqbot.start()
        scheduler.start()
        print("Running...")
        input()
        print("Stopping...")
    except KeyboardInterrupt:
        pass
