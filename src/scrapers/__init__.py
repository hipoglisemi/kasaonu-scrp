
try:
    from .garanti_bonus import GarantiBonusScraper  # type: ignore # pyre-ignore[21]
except ImportError: GarantiBonusScraper = None

try:
    from .garanti_milesandsmiles import GarantiMilesAndSmilesScraper  # type: ignore # pyre-ignore[21]
except ImportError: GarantiMilesAndSmilesScraper = None

try:
    from .garanti_shopandfly import GarantiShopAndFlyScraper  # type: ignore # pyre-ignore[21]
except ImportError: GarantiShopAndFlyScraper = None

try:
    from .vodafone import VodafoneScraper  # type: ignore # pyre-ignore[21]
except ImportError: VodafoneScraper = None

try:
    from .akbank_axess import AkbankAxessScraper  # type: ignore # pyre-ignore[21]
except ImportError: AkbankAxessScraper = None

try:
    from .akbank_free import AkbankFreeScraper  # type: ignore # pyre-ignore[21]
except ImportError: AkbankFreeScraper = None

try:
    from .akbank_business import AkbankBusinessScraper  # type: ignore # pyre-ignore[21]
except ImportError: AkbankBusinessScraper = None

try:
    from .enpara import EnparaScraper  # type: ignore # pyre-ignore[21]
except ImportError: EnparaScraper = None

try:
    from .turktelekom import TurkTelekomScraper  # type: ignore # pyre-ignore[21]
except ImportError: TurkTelekomScraper = None

try:
    from .opet import OpetScraper  # type: ignore # pyre-ignore[21]
except ImportError: OpetScraper = None

try:
    from .ziraat import ZiraatScraper # type: ignore # pyre-ignore[21]
except ImportError: ZiraatScraper = None

try:
    from .petrolofisi import PetrolOfisiScraper # type: ignore # pyre-ignore[21]
except ImportError: PetrolOfisiScraper = None

try:
    from .shell import ShellScraper # type: ignore # pyre-ignore[21]
except ImportError: ShellScraper = None

try:
    from .totalenergies import TotalEnergiesScraper # type: ignore # pyre-ignore[21]
except ImportError: TotalEnergiesScraper = None

try:
    from .on_digital import ONDigitalScraper # type: ignore # pyre-ignore[21]
except ImportError: ONDigitalScraper = None

try:
    from .ahlpay import AhlpayScraper # type: ignore # pyre-ignore[21]
except ImportError: AhlpayScraper = None


try:
    from .emlakkatilim import EmlakKatilimScraper # type: ignore # pyre-ignore[21]
except ImportError: EmlakKatilimScraper = None

try:
    from .anadolubank import AnadolubankScraper # type: ignore # pyre-ignore[21]
except ImportError: AnadolubankScraper = None

try:
    from .tkpay import TkpayScraper # type: ignore # pyre-ignore[21]
except ImportError: TkpayScraper = None


__all__ = [
    'GarantiBonusScraper',
    'GarantiMilesAndSmilesScraper',
    'GarantiShopAndFlyScraper',
    'VodafoneScraper',
    'AkbankAxessScraper',
    'AkbankFreeScraper',
    'AkbankBusinessScraper',
    'EnparaScraper',
    'TurkTelekomScraper',
    'OpetScraper',
    'ZiraatScraper',
    'PetrolOfisiScraper',
    'ShellScraper',
    'TotalEnergiesScraper',
    'ONDigitalScraper',
    'AhlpayScraper',
    'EmlakKatilimScraper',
    'AnadolubankScraper',
    'TkpayScraper'
]
