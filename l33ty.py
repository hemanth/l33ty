#!/usr/bin/env python
''' A PY IRC bot with functionalities like:
    * l33t translation 
    * Google I'm feeling lucky search 
    * Karma system nick++ or nick--
    * XCKD random images
    * Flipping a coin, throwing the dice
'''

import sys
import operator
import math
import re
import random
import os
import urllib
import json
import datetime
import BeautifulSoup
import bsddb
from twisted.internet import reactor, task, defer, protocol
from twisted.python import log
from twisted.words.protocols import irc
from twisted.web.client import getPage
from twisted.web.client import Agent
from twisted.application import internet, service
from twisted.web import google, client
from twisted.web.http_headers import Headers

__author__ = "Hemanth HM <hemanth.hm@gmail.com>"
__license__ = "GNU GPLV3"
__version__ = "1.0" 

''' Server and the port where the bot is to be hosted '''
HOST, PORT = 'irc.freenode.net', 6667

''' RPN calc map operator symbol tuple of # and function '''
calc_operators = {
    '+': (2, operator.add),
    '-': (2, operator.sub),
    '*': (2, operator.mul),
    '/': (2, operator.truediv),
    '//': (2, operator.div),
    '%': (2, operator.mod),
    '^': (2, operator.pow),
    'abs': (1, abs),
    'ceil': (1, math.ceil),
    'floor': (1, math.floor),
    'round': (2, round),
    'trunc': (1, int),
    'log': (2, math.log),
    'ln': (1, math.log),
    'pi': (0, lambda: math.pi),
    'e': (0, lambda: math.e),
}


class LeetyIRC(irc.IRCClient):
    ''' The nick name of the bot '''
    nickname = 'l33ty'

    ''' After server has acknowledged the nick '''
    def signedOn(self):
        self.join(self.factory.channels)
    
    ''' When a PM is recived '''
    def privmsg(self, user, channel, message):
        nick, _, host = user.partition('!')
        if channel != self.nickname and not message.startswith(self.nickname):
            # We can LOG here :)
            file = open('log', 'a')
            file.writelines(nick+" "+datetime.datetime.now().strftime("%Y-%m-%d [%H:%M]")+" : "+message+"\n")
            return
        # Strip off any addressing. 
        message = re.sub(
            r'^%s[.,>:;!?]*\s*' % re.escape(self.nickname), '', message)
        command, _, rest = message.partition(' ')
        
        # Get the function 
        func = getattr(self, 'command_' + command, None)
        
        # IF not a defined function
        if func is None:
            self.msg(channel, "%s,I cant understand what %s means, but you can teach me, catch me @ http://github.com/hemanth/l33ty" % (nick,message))
            return 
        
        d = defer.maybeDeferred(func, rest)
        if channel == self.nickname:
            args = [nick]
        # If there is rediction request made in the bot query.
        elif len(rest.split('>')) > 1:
            args = [channel, rest.split('>')[1]]
        else:
            args = [channel, nick]
        d.addCallbacks(self._send_message(*args), self._show_error(*args))
        return message
    
    def _send_message(self, target, nick=None):
        def callback(msg):
            print target
            if nick:
                msg = '%s, %s' % (nick, msg)
            self.msg(target, msg)
        return callback
    
    def _show_error(self, target, nick=None):
        def errback(f):
            msg = f.getErrorMessage()
            if nick:
                msg = '%s, %s' % (nick, msg)
            self.msg(target, msg)
            return f
        return errback
        
    ''' Command_xxx corresponds to factoids of the bot '''
    
    def command_help(self,rest):
        ''' Just returns the help msg, to the user who pinged with help '''
        return "Try l33t <str>, peep <url>,goog <str>, xkcd, flip, flop, roll, fortune, karma nick++/--"
       
    def command_hi(self,rest):
        return "Hello :)"

    def command_l33t(self,rest):
        ''' This method does the l33t translation, with the use of web API '''
        url='http://nyhacker.org/~hemanth.hm/hacks/t.php?'+urllib.quote(rest)
        ''' getPage() returns a deferred '''  
        d = getPage(url)
        ''' add a call back, that would just return the page contents '''
        d.addCallback(self._get_page_content, url)
        return d
        
    def _get_page_content(self,page,url):
         return page
    
    def command_karma(self,rest):
          ''' This method maintains a karma system bsddb is used. '''
          kdb = bsddb.btopen('karma.db', 'c')
          whom, _, what = rest.partition(' ')
          try:
              if(whom == self.nick):
                  kdb[whom]=str(int(kdb[whom])-1)
                  # The user can't ++ his own karam
                  return "To smart! "+whom+"'s karma is : "+kdb[whom]
              if(what == "++"):
                  kdb[whom]=str(int(kdb[whom])+1)
              elif(what == "--"):
                  kdb[whom]=str(int(kdb[whom])-1)
          except KeyError:
              # The user is been added to the karma system
              kdb[whom]="1"
          return "Karma! Karma!"+whom+"'s karma is : "+kdb[whom]

    def command_flop(self,rest):
        return "Filp it!"
        
    def command_flip(self,rest):
        return random.choice(('head', 'tail'))
        
    def command_roll(self,rest):
        return random.choice((1,2,3,4,5,6))
    
    def command_fortune(self,rest):
        return os.popen('fortune -n 111').read().translate(None, '\n\r\t')
        
    def command_goog(self,rest):
        ''' rest is the rest of the query for goog <str> passed by the user
            that is encoded and is queried with the help of google search
            API, a callback is added after getpage() '''
        if(rest == "" or rest == " "):
           rest = "google"
        query = urllib.urlencode({'q': rest})
        url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&%s' % query
        search_response_d = getPage(url)
        search_response_d.addCallback(self._get_json_results,url)
        return search_response_d

    def _get_json_results(self,page,url):
        ''' The return value from Google API is json,
            from which the first link is extracted '''
        search_results = page.decode("utf8")
        results = json.loads(search_results)
        return "".join(str(results['responseData']['results'][0]['url']))

        
    def command_peep(self, url):
        d = getPage(url)
        d.addCallback(self._parse_pagetitle, url)
        return d

    def command_xkcd(self,rest):
        ''' Agent is used to get the redirected URL
             /random/comic will redirect to a new
             comic that is fetched from cbRequest '''
        agent = Agent(reactor)
        d = agent.request(
        'GET',
        'http://dynamic.xkcd.com/random/comic/',
        Headers({'User-Agent': ['Twisted Web Client Example']}),
        None)
        d.addCallback(self.cbRequest)
        return d
         
    def cbRequest(self,response):
         ''' Get the redirected url is retrieved from getRawHeaders() '''
         return "".join(response.headers.getRawHeaders("location")) + " Enjoy it!"

         
    def _parse_pagetitle(self, page, url):
        ''' Get the page title '''
        head_tag = BeautifulSoup.SoupStrainer('head')
        soup = BeautifulSoup.BeautifulSoup(page, 
            parseOnlyThese=head_tag, convertEntities=['html', 'xml'])
        if soup.title is None:
            return '%s -- no title found' % url
        title = unicode(soup.title.string).encode('utf-8')
        return '%s -- "%s"' % (url, title)

    def command_calc(self, rest):
        '''RPN calculator!'''
        stack = []
        for tok in rest.split():
            if tok in calc_operators:
                n_pops, func = calc_operators[tok]
                args = [stack.pop() for x in xrange(n_pops)]
                args.reverse()
                stack.append(func(*args))
            elif '.' in tok:
                stack.append(float(tok))
            else:
                stack.append(int(tok))
        result = str(stack.pop())
        if stack:
            result += ' (warning: %d item(s) left on stack)' % len(stack)
        return result

class LeetyIRCactory(protocol.ReconnectingClientFactory):
    protocol = LeetyIRC
    channels = '#testingbot'

if __name__ == '__main__':
    reactor.connectTCP(HOST, PORT, LeetyIRCactory())
    log.startLogging(sys.stdout)
    reactor.run()

elif __name__ == '__builtin__':
    
    application = service.Application('LeetyIRCBot')
   
    ircService = internet.TCPClient(HOST, PORT, LeetyIRCactory())
    ircService.setServiceParent(application)



