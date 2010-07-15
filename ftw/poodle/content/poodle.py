from zope.interface import implements

try:
    from Products.LinguaPlone import public as atapi
except ImportError:
    from Products.Archetypes import atapi

from AccessControl import ClassSecurityInfo
from Products.ATContentTypes.content import base

from Products.ATContentTypes.content import schemata
from Products.CMFCore import permissions
from Products.CMFCore.utils import getToolByName

from Products.DataGridField import DataGridField, DataGridWidget
from Products.DataGridField.Column import Column
from zope.component import getMultiAdapter, queryMultiAdapter, queryUtility
from ftw.arbeitsraum.interfaces import IArbeitsraumUtils

from ftw.poodle import poodleMessageFactory as _
from ftw.poodle.interfaces import IPoodle, IPoodleConfig
from ftw.poodle.config import PROJECTNAME

from ftw.utils.users import getAssignableUsers

PoodleSchema = schemata.ATContentTypeSchema.copy() + atapi.Schema((
    atapi.LinesField(
        name='users',
        vocabulary="getPossibleUsers",
        widget=atapi.InAndOutWidget
        (
            label="Users",
            label_msgid='ftwpoodle_label_users',
            i18n_domain='ftwpoodle',
        ),
        required=1,
        multivalued=1
    ),

    DataGridField(
        name='dates',
        allow_empty_rows = False,
        widget=DataGridWidget(
            auto_insert = True,  
            columns= {"date": Column(_(u"ftwpoodle_desc_date", default="Date (TT. MM. JJJJ)")), "duration": Column(_(u"ftwpoodle_desc_duration", default="Time / Duration"))},
            label='Dates',
            label_msgid='ftwpoodle_label_dates',
            i18n_domain='ftwpoodle',
        ),
        columns= ("date", "duration")
    ),
))

schemata.finalizeATCTSchema(PoodleSchema, moveDiscussion=False)


class Poodle(base.ATCTContent):
    """ A 'doodle'-like content type that helps finding a date for a meeting """
    implements(IPoodle)
    
    security = ClassSecurityInfo()
    
    portal_type = "Meeting poll"
    schema = PoodleSchema

    security.declarePrivate("getPossibleUsers")
    def getPossibleUsers(self):
        return getAssignableUsers(self,'Reader', show_contacts=False)

    #sort list, because we get an tuple (not a list)
    def getUsers(self):
        sorted_users = []
        for u in getAssignableUsers(self,'Reader', show_contacts=False):
            if u[0] in self.getField('users').get(self):
                sorted_users.append(u[0])
        return sorted_users
        

#    def setDatesForUser(user, dates):
#        if user not in self.getUsers() or len(self.poodledata[user]) > 0: 
#            return False # user not allowed to vote or already voted
#        self.poodledata[user] = dates
#        return 

    security.declarePrivate("getDatesHash")
    def getAviableChoices(self):
        return [str(hash('%s%s' % (a['date'],a['duration']))) for a in self.getDates()]

    security.declarePrivate("getPoodleData")
    def getPoodleData(self):
        if IPoodle.providedBy(self):
            return IPoodleConfig(self).getPoodleData()
        return {}
    
    security.declarePrivate("setPoodleData")
    def setPoodleData(self, data):
        if IPoodle.providedBy(self):
            IPoodleConfig(self).setPoodleData(data)

    security.declarePrivate("updatePoodleData")        
    def updatePoodleData(self):
        poodledata = self.getPoodleData()
        poodledata = self.updateDates(poodledata)
        poodledata = self.updateUsers(poodledata)
        self.setPoodleData(poodledata)
        self.updateSharing()
        
    security.declarePrivate("updateSharing")
    def updateSharing(self):
        """ 
        Allow the selected Users to view the object
        """
        users = self.getUsers()
        wanted_roles = [u'Reader',]
        for user in users:
            self.manage_setLocalRoles(user, wanted_roles)
        self.reindexObjectSecurity()
        # XXX: remove users?

    security.declarePrivate("updateDates")
    def updateDates(self, poodledata):
        dates = self.getDates()
        poodledata["dates"] = [i['date'] for i in dates]
        poodledata['ids'] = self.getAviableChoices()
        return poodledata
        
    security.declarePrivate("updateUsers")
    def updateUsers(self, poodledata):
        users = self.getUsers()
        choices = poodledata['ids']
        for user in users:
            if user not in poodledata.keys():
                # add user to data and fill dates with None
                userdates = {}
                [userdates.setdefault(choice) for choice in choices]
                poodledata[user] = userdates                    
            else:
                # check if the dates are correct
                userdates = poodledata[user]
                for choice in choices:
                    if choice not in userdates.keys():
                        # a new date
                        userdates[choice] = None
        # check if we need to remove any users from poodledata
        for user in poodledata.keys():
            if user not in ['dates', 'ids'] and user not in users:
                del(poodledata[user])
        return poodledata
    
    security.declarePrivate("saveUserData")
    def saveUserData(self, userid, dates):
        poodledata = self.getPoodleData()
        if userid in poodledata.keys():
            for date in poodledata["dates"]:
                if date in dates:
                    poodledata[userid][date] = True
                else: 
                    poodledata[userid][date] = False
        self.setPoodleData(poodledata)

    security.declarePrivate("sendNotification")    
    def sendNotification(self, user):
        """Sends a notification after someone filled out the meeting poll"""
        mtool = getToolByName(self, "portal_membership") 
        portal = getToolByName(self, 'portal_url').getPortalObject()
        site_properties = getToolByName(self, 'portal_properties').site_properties
        
        host = getToolByName(self, "MailHost")
        creator = self.Creator() # send a mail to the creator of the poll
        send_to_address = mtool.getMemberById(creator).getProperty('email')
        if send_to_address == '': send_to_address = site_properties.email_from_address
        send_from_address = site_properties.email_from_address
        # XXX: translation not working!
        #subject = u"%s %s" % (_(u"ftwpoodle_mail_subject", default="Update on meeting poll at"), self.absolute_url())
        subject = u"%s %s" % ("Update der Sitzungsumfrage unter", self.absolute_url())

        template = getattr(self, 'poodle_notification')
        encoding = portal.getProperty('email_charset')
        envelope_from = send_from_address
        # Cook from template
        message = template(self,  username=user, url=self.absolute_url())
        result = host.secureSend(message, send_to_address,
                                 envelope_from, subject=subject,
                                 subtype='plain', charset=encoding,
                                 debug=False, From=send_from_address)    

    security.declarePrivate("getStats") 
    def getStats(self):
        data = self.getPoodleData()
        dates = data.get('dates')
        users = [u for u in data.keys() if u != 'dates']
        result = {}
        for date in dates:
            result[date] = 0
        for user in users:
            for date in data[user]: 
                if date == True: result[date] += 1
            
        return result
            
        
atapi.registerType(Poodle, PROJECTNAME)