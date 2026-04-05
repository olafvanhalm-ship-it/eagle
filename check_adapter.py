import sys
sys.path.insert(0, 'Application')
sys.path.insert(0, r'Application\Adapters\Input adapters\M adapter')
from m_adapter import MAdapter
import glob
templates = glob.glob(r'Application\Adapters\Input adapters\M adapter\golden_set\*\*.xlsx')
if templates:
    t = templates[0]
    print(f'Using: {t}')
    a = MAdapter(t)
    print('Has aifm_report:', hasattr(a, 'aifm_report'))
    print('Has aif_reports:', hasattr(a, 'aif_reports'))
    print('Has source_canonical:', hasattr(a, 'source_canonical'))
    attrs = [x for x in dir(a) if not x.startswith('_') and 'report' in x.lower()]
    print('Report attrs:', attrs)
    all_attrs = [x for x in dir(a) if not x.startswith('_')]
    print('All public attrs:', all_attrs)
else:
    print('No test templates found')
