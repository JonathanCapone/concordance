"""Ground Truth — reading Canada's public record as a hundred-year instrument.

The Internet Archive Canada government publications collection is 104,241
documents and 22.1 million scanned pages. Inside them are measurements of the
physical condition of Canada, town by town, from 1841 onward. The median
document has been downloaded 90 times.

Every civil servant who wrote a measurement down was a node in a sensor network
that ran for 150 years and was never once read as a network. This package reads
it back out.
"""

from .models import PageText, Provenance, Record

__version__ = "0.1.0"

__all__ = ["PageText", "Provenance", "Record"]
