"""
AI Agents for Music Production
10 specialized agents for complete audio production pipeline
"""

from .base import StudioAgent
from .orchestrateur import Orchestrateur
from .analyste import Analyste
from .chirurgien import Chirurgien
from .compositeur import Compositeur
from .arrangeur import Arrangeur
from .ingenieur_son import IngenieurSon
from .mastering import MasteringEngineer
from .dj_pro import DJPro
from .expert_vocal import ExpertVocal
from .superviseur import Superviseur
from .gardien import Gardien
from .compositeur_autonome import CompositeurAutonome
from .chef_supreme import ChefSupreme
from .distributeur import Distributeur
from .transcripteur import Transcripteur
from .ingenieur_vst import IngenieurVST
from .directeur_artistique import DirecteurArtistique

__all__ = [
    'StudioAgent',
    'Orchestrateur',
    'Analyste',
    'Chirurgien',
    'Compositeur',
    'Arrangeur',
    'IngenieurSon',
    'MasteringEngineer',
    'DJPro',
    'ExpertVocal',
    'Superviseur',
    'Gardien',
    'CompositeurAutonome',
    'ChefSupreme',
    'Distributeur',
    'Transcripteur',
    'IngenieurVST',
    'DirecteurArtistique'
]