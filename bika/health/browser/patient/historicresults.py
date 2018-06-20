# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.HEALTH
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api
from bika.lims.browser import BrowserView
from bika.health import bikaMessageFactory as _
from bika.lims.catalog.analysisrequest_catalog import \
    CATALOG_ANALYSIS_REQUEST_LISTING
from bika.lims.catalog.analysis_catalog import CATALOG_ANALYSIS_LISTING
from zope.interface import implements
from plone.app.layout.globals.interfaces import IViewView
from Products.CMFPlone.i18nl10n import ulocalized_time
import plone
import json


class HistoricResultsView(BrowserView):
    implements(IViewView)

    template = ViewPageTemplateFile("historicresults.pt")

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        self.context = context
        self.request = request
        self._rows = None
        self._dates = None
        path = "/++resource++bika.health.images"
        self.icon = self.portal_url + path + "/historicresults_big.png"
        self.title = self.context.translate(_("Historic Results"))
        self.description = ""

    def __call__(self):
        self._load()
        return self.template()

    def get_dates(self):
        """ Gets the result capture dates for which at least one analysis
            result has been found for the current Patient.
        """
        return self._dates

    def get_rows(self):
        """ Returns a dictionary with rows with the following structure:
            rows = {<sampletype_uid>: {
                        'object': <sampletype>,
                        'analyses': {
                            <analysisservice_uid>: {
                                'object': <analysisservice>,
                                'title': <analysisservice.title>,
                                'units': <analysisservice.units>,
                                'specs': {'error', 'min', 'max', ...},
                                <date> : {
                                    'object': <analysis>,
                                    'result': <analysis.result>,
                                    'date': <analysis.resultdate>
                                },
                            }
                        }
                    }}
        """
        return self._rows

    def _load(self):
        """ Loads the Controller acessors and other stuff
        """
        self._dates, self._rows = get_historicresults(self.context)


def get_historicresults(patient):
    if not patient:
        return [], {}

    rows = {}
    dates = []
    states = ['verified', 'published']

    # Retrieve the AR IDs for the current patient
    query = dict(getPatientUID=api.get_uid(patient))
    ars = api.search(query, catalog=CATALOG_ANALYSIS_REQUEST_LISTING)
    ar_uids = map(api.get_uid, ars)

    # Retrieve all the analyses, sorted by ResultCaptureDate DESC
    query = dict(getRequestUID=ar_uids, sort_on='getResultCaptureDate',
                 sort_order='reverse')
    analyses = api.search(query, catalog=CATALOG_ANALYSIS_LISTING)

    # Build the dictionary of rows
    for analysis in analyses:
        analysis = api.get_object(analysis)
        ar = analysis.getRequest()
        sample_type = ar.getSampleType()
        if not sample_type:
            continue
        sample_type_uid = api.get_uid(sample_type)
        row = rows.get(sample_type_uid, dict(object=sample_type, analyses={}))
        anrow = row.get('analyses')
        service_uid = analysis.getServiceUID()
        asdict = anrow.get(service_uid, {'object': analysis,
                                         'title': analysis.Title(),
                                         'keyword': analysis.getKeyword(),
                                         'units': analysis.getUnit()})
        cap_date = analysis.getResultCaptureDate()
        cap_date = api.is_date(cap_date) and \
                   cap_date.strftime('%Y-%m-%d %I:%M %p') or ''
        if not cap_date:
            return

        # If more than one analysis of the same type has been
        # performed in the same datetime, get only the last one
        if cap_date not in asdict.keys():
            asdict[cap_date] = {'object': analysis,
                                'result': analysis.getResult(),
                                'formattedresult': analysis.getFormattedResult()}
            # Get the specs
            # Only the specs applied to the last analysis for that
            # sample type will be taken into consideration.
            # We assume specs from previous analyses are obsolete.
            if 'specs' not in asdict.keys():
                specs = analysis.getResultsRange()
                if not specs.get('rangecomment', ''):
                    if specs.get('min', '') and specs.get('max', ''):
                        specs['rangecomment'] = '%s - %s' % \
                            (specs.get('min'), specs.get('max'))
                    elif specs.get('min', ''):
                        specs['rangecomment'] = '> %s' % specs.get('min')
                    elif specs.get('max', ''):
                        specs['rangecomment'] = '< %s' % specs.get('max')

                    if specs.get('error', '0') != '0' \
                            and specs.get('rangecomment', ''):
                        specs['rangecomment'] = ('%s (%s' %
                                                 (specs.get('rangecomment'),
                                                  specs.get('error'))) + '%)'
                asdict['specs'] = specs

            if cap_date not in dates:
                dates.append(cap_date)
        anrow[service_uid] = asdict
        row['analyses'] = anrow
        rows[sample_type_uid] = row
    dates.sort(reverse=False)

    return dates, rows


class historicResultsJSON(BrowserView):
    """ Returns a JSON array datatable in a tabular format.
    """

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        self.context = context
        self.request = request

    def __call__(self):
        dates, data = get_historicresults(self.context)
        datatable = []
        for andate in dates:
            datarow = {'date': ulocalized_time(
                andate, 1, None, self.context, 'bika')}
            for row in data.itervalues():
                for anrow in row['analyses'].itervalues():
                    serie = anrow['title']
                    datarow[serie] = anrow.get(andate, {}).get('result', '')
            datatable.append(datarow)
        return json.dumps(datatable)
