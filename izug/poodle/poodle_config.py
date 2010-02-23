from zope.interface import implements
from zope.component import adapts
from zope.annotation.interfaces import IAnnotations
from interfaces import IPoodle, IPoodleConfig
from persistent.dict import PersistentDict 


class PoodleConfig(object):
    implements(IPoodleConfig)
    adapts(IPoodle)
    
    def __init__(self, context):
        self.context = context
        self.annotations = IAnnotations(self.context)
    
    def getPoodleData(self):
        return self.annotations.get('poodledata', PersistentDict({}))
    
    def setPoodleData(self, data):
        if data:
            self.annotations['poodledata'] = PersistentDict(data)
            

    
