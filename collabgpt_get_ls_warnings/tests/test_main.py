import json
import pytest
import azure.functions as func

from collabgpt_get_ls_warnings import main, filter_items


class TestLSWarnings:
    @pytest.mark.parametrize('org, filter_type, location, project_code, threshold', [
        ('CHEVRON', 'RoadTransportJobHCRTransitTimeExceededWarning', None, None, None),
        ('CHEVRON', 'HcrDwellTimeExceededAtLocation', 'barrowislandrevlog', None, None),
        ('CHEVRON', 'HcrDwellTimeExceededAtLocation', 'barrowislandrevlog', None, '5'),
        ('CHEVRON', 'HcrDwellTimeExceededAtLocation', 'barrowislandrevlog', None, 5),
        ('CHEVRON', 'HcrDwellTimeExceededAtLocation', 'barrowislandrevlog', None, 'five'),
        ('CHEVRON', 'DangerousGoodsWarning', None, None, None),
        ('CHEVRON', None, None, None, None),
        ('Fake Company 1', None, None, None, None),
        ('CHEVRON', 'VoyageManifestMissingInSequence', None, None, None),  # not supported
        (None, None, None, None, None),
    ])
    def test_basic_request(self, org, filter_type, location, project_code, threshold):
        """Basic request test, does not depend on any data being return, only the params work as expected
        """
        data = dict(
            organization=org,
            filter_type=filter_type,
            location=location,
            project_code=project_code,
            threshold=threshold
        )

        req = func.HttpRequest(
            method='GET',
            body=json.dumps(data).encode('utf-8'),
            url='/api/collabgpt_http_lc',
            params=None)

        response = main(req)
        assert response.status_code == 200
