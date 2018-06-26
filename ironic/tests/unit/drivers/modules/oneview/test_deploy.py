# Copyright (2015-2017) Hewlett Packard Enterprise Development LP
# Copyright (2015-2017) Universidade Federal de Campina Grande
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from ironic.common import exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conf import CONF
from ironic.drivers.modules import agent
from ironic.drivers.modules import iscsi_deploy
from ironic.drivers.modules.oneview import common
from ironic.drivers.modules.oneview import deploy
from ironic.drivers.modules.oneview import deploy_utils
from ironic.tests.unit.drivers.modules.oneview import test_common
from ironic.tests.unit.objects import utils as obj_utils

METHODS = ['iter_nodes', 'update_node', 'do_provisioning_action']

oneview_error = common.SERVER_HARDWARE_ALLOCATION_ERROR
maintenance_reason = common.NODE_IN_USE_BY_ONEVIEW

driver_internal_info = {'oneview_error': oneview_error}
nodes_taken_by_oneview = [(1, 'oneview')]
nodes_freed_by_oneview = [(1, 'oneview', maintenance_reason)]
nodes_taken_on_cleanfail = [(1, 'oneview', driver_internal_info)]
nodes_taken_on_cleanfail_no_info = [(1, 'oneview', {})]

GET_POWER_STATE_RETRIES = 5


def _setup_node_in_available_state(node):
    node.provision_state = states.AVAILABLE
    node.maintenance = False
    node.maintenance_reason = None
    node.save()


def _setup_node_in_manageable_state(node):
    node.provision_state = states.MANAGEABLE
    node.maintenance = True
    node.maintenance_reason = common.NODE_IN_USE_BY_ONEVIEW
    node.save()


def _setup_node_in_cleanfailed_state_with_oneview_error(node):
    node.provision_state = states.CLEANFAIL
    node.maintenance = False
    node.maintenance_reason = None
    driver_internal_info = node.driver_internal_info
    oneview_error = common.SERVER_HARDWARE_ALLOCATION_ERROR
    driver_internal_info['oneview_error'] = oneview_error
    node.driver_internal_info = driver_internal_info
    node.save()


def _setup_node_in_cleanfailed_state_without_oneview_error(node):
    node.provision_state = states.CLEANFAIL
    node.maintenance = False
    node.maintenance_reason = None
    node.save()


class OneViewDriverDeploy(deploy.OneViewPeriodicTasks):
    oneview_driver = 'oneview'


@mock.patch('ironic.objects.Node', spec_set=True, autospec=True)
@mock.patch.object(deploy_utils, 'is_node_in_use_by_oneview')
class OneViewPeriodicTasks(test_common.BaseOneViewTest):

    def setUp(self):
        super(OneViewPeriodicTasks, self).setUp()
        self.config(manager_url='https://1.2.3.4', group='oneview')
        self.config(username='user', group='oneview')
        self.config(password='password', group='oneview')

        self.deploy = OneViewDriverDeploy()
        self.os_primary = mock.MagicMock(spec=METHODS)

    def test_node_manageable_maintenance_when_in_use_by_oneview(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_available_state(self.node)
        self.os_primary.iter_nodes.return_value = nodes_taken_by_oneview
        mock_is_node_in_use_by_oneview.return_value = True
        self.deploy._periodic_check_nodes_taken_by_oneview(
            self.os_primary, self.context
        )
        mock_is_node_in_use_by_oneview.assert_called_once_with(self.node)
        self.assertTrue(self.os_primary.update_node.called)
        self.assertTrue(self.os_primary.do_provisioning_action.called)
        self.assertTrue(self.node.maintenance)
        self.assertEqual(common.NODE_IN_USE_BY_ONEVIEW,
                         self.node.maintenance_reason)

    def test_node_stay_available_when_not_in_use_by_oneview(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_available_state(self.node)
        mock_node_get.return_value = self.node
        mock_is_node_in_use_by_oneview.return_value = False
        self.os_primary.iter_nodes.return_value = nodes_taken_by_oneview
        self.deploy._periodic_check_nodes_taken_by_oneview(
            self.os_primary, self.context
        )
        mock_is_node_in_use_by_oneview.assert_called_once_with(self.node)
        self.assertFalse(self.os_primary.update_node.called)
        self.assertFalse(self.os_primary.do_provisioning_action.called)
        self.assertFalse(self.node.maintenance)
        self.assertIsNone(self.node.maintenance_reason)

    def test_node_stay_available_when_raise_exception(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_available_state(self.node)
        side_effect = exception.OneViewError('boom')
        mock_is_node_in_use_by_oneview.side_effect = side_effect
        self.os_primary.iter_nodes.return_value = nodes_taken_by_oneview
        self.deploy._periodic_check_nodes_taken_by_oneview(
            self.os_primary, self.context
        )
        mock_is_node_in_use_by_oneview.assert_called_once_with(self.node)
        self.assertFalse(self.os_primary.update_node.called)
        self.assertFalse(self.os_primary.do_provisioning_action.called)
        self.assertFalse(self.node.maintenance)
        self.assertNotEqual(common.NODE_IN_USE_BY_ONEVIEW,
                            self.node.maintenance_reason)

    def test_node_available_when_not_in_use_by_oneview(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_manageable_state(self.node)
        self.os_primary.iter_nodes.return_value = nodes_freed_by_oneview
        mock_is_node_in_use_by_oneview.return_value = False
        self.deploy._periodic_check_nodes_freed_by_oneview(
            self.os_primary, self.context
        )
        mock_is_node_in_use_by_oneview.assert_called_once_with(self.node)
        self.assertTrue(self.os_primary.update_node.called)
        self.assertTrue(self.os_primary.do_provisioning_action.called)
        self.assertFalse(self.node.maintenance)
        self.assertIsNone(self.node.maintenance_reason)

    def test_node_stay_manageable_when_in_use_by_oneview(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_manageable_state(self.node)
        mock_is_node_in_use_by_oneview.return_value = True
        self.os_primary.iter_nodes.return_value = nodes_freed_by_oneview
        self.deploy._periodic_check_nodes_freed_by_oneview(
            self.os_primary, self.context
        )
        mock_is_node_in_use_by_oneview.assert_called_once_with(self.node)
        self.assertFalse(self.os_primary.update_node.called)
        self.assertFalse(self.os_primary.do_provisioning_action.called)
        self.assertTrue(self.node.maintenance)
        self.assertEqual(common.NODE_IN_USE_BY_ONEVIEW,
                         self.node.maintenance_reason)

    def test_node_stay_manageable_maintenance_when_raise_exception(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_manageable_state(self.node)
        side_effect = exception.OneViewError('boom')
        mock_is_node_in_use_by_oneview.side_effect = side_effect
        self.os_primary.iter_nodes.return_value = nodes_freed_by_oneview
        self.deploy._periodic_check_nodes_freed_by_oneview(
            self.os_primary, self.context
        )
        mock_is_node_in_use_by_oneview.assert_called_once_with(self.node)
        self.assertFalse(self.os_primary.update_node.called)
        self.assertFalse(self.os_primary.do_provisioning_action.called)
        self.assertTrue(self.node.maintenance)
        self.assertEqual(common.NODE_IN_USE_BY_ONEVIEW,
                         self.node.maintenance_reason)

    def test_node_manageable_maintenance_when_oneview_error(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_cleanfailed_state_with_oneview_error(self.node)
        self.os_primary.iter_nodes.return_value = nodes_taken_on_cleanfail
        self.deploy._periodic_check_nodes_taken_on_cleanfail(
            self.os_primary, self.context
        )
        self.assertTrue(self.os_primary.update_node.called)
        self.assertTrue(self.os_primary.do_provisioning_action.called)
        self.assertTrue(self.node.maintenance)
        self.assertEqual(common.NODE_IN_USE_BY_ONEVIEW,
                         self.node.maintenance_reason)
        self.assertNotIn('oneview_error', self.node.driver_internal_info)

    def test_node_stay_clean_failed_when_no_oneview_error(
        self, mock_is_node_in_use_by_oneview, mock_node_get
    ):
        mock_node_get.get.return_value = self.node
        _setup_node_in_cleanfailed_state_without_oneview_error(self.node)
        self.os_primary.iter_nodes.return_value = (
            nodes_taken_on_cleanfail_no_info)
        self.deploy._periodic_check_nodes_taken_on_cleanfail(
            self.os_primary, self.context
        )
        self.assertFalse(self.os_primary.update_node.called)
        self.assertFalse(self.os_primary.do_provisioning_action.called)
        self.assertFalse(self.node.maintenance)
        self.assertNotEqual(common.NODE_IN_USE_BY_ONEVIEW,
                            self.node.maintenance_reason)
        self.assertNotIn('oneview_error', self.node.driver_internal_info)


class OneViewIscsiDeployTestCase(test_common.BaseOneViewTest):

    deploy_interface = 'oneview-iscsi'

    def setUp(self):
        super(OneViewIscsiDeployTestCase, self).setUp()
        self.config(manager_url='https://1.2.3.4', group='oneview')
        self.config(username='user', group='oneview')
        self.config(password='password', group='oneview')

        self.port = obj_utils.create_test_port(self.context,
                                               node_id=self.node.id)
        self.info = common.get_oneview_info(self.node)

    def test_get_properties(self):
        expected = common.COMMON_PROPERTIES
        self.assertEqual(expected,
                         deploy.OneViewIscsiDeploy().get_properties())

    @mock.patch.object(common, 'validate_oneview_resources_compatibility',
                       spect_set=True, autospec=True)
    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'validate',
                       spec_set=True, autospec=True)
    def test_validate(
            self, iscsi_deploy_validate_mock, mock_validate):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.validate(task)
            self.assertTrue(mock_validate.called)
            iscsi_deploy_validate_mock.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'prepare', autospec=True)
    @mock.patch.object(deploy_utils, 'allocate_server_hardware_to_ironic')
    def test_prepare(self, allocate_server_hardware_mock,
                     iscsi_deploy_prepare_mock):
        self.node.provision_state = states.DEPLOYING
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.deploy.prepare(task)
            iscsi_deploy_prepare_mock.assert_called_once_with(mock.ANY, task)
            self.assertTrue(allocate_server_hardware_mock.called)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'prepare',
                       spec_set=True, autospec=True)
    def test_prepare_active_node(self, iscsi_deploy_prepare_mock):
        """Ensure nodes in running states are not inadvertently changed"""
        test_states = list(states.STABLE_STATES)
        test_states.extend([states.CLEANING,
                           states.CLEANWAIT,
                           states.INSPECTING])
        for state in test_states:
            self.node.provision_state = state
            self.node.save()
            iscsi_deploy_prepare_mock.reset_mock()
            with task_manager.acquire(self.context, self.node.uuid,
                                      shared=False) as task:
                task.driver.deploy.prepare(task)
                iscsi_deploy_prepare_mock.assert_called_once_with(
                    mock.ANY, task)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'deploy',
                       spec_set=True, autospec=True)
    def test_deploy(self, iscsi_deploy_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.deploy(task)
            iscsi_deploy_mock.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'tear_down', spec_set=True,
                       autospec=True)
    def test_tear_down(self, iscsi_tear_down_mock):
        iscsi_tear_down_mock.return_value = states.DELETED
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            returned_state = task.driver.deploy.tear_down(task)
            iscsi_tear_down_mock.assert_called_once_with(mock.ANY, task)
            self.assertEqual(states.DELETED, returned_state)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'tear_down', spec_set=True,
                       autospec=True)
    @mock.patch.object(deploy_utils, 'deallocate_server_hardware_from_ironic')
    def test_tear_down_with_automated_clean_disabled(
            self, deallocate_server_hardware_mock, iscsi_tear_down_mock):
        CONF.conductor.automated_clean = False
        iscsi_tear_down_mock.return_value = states.DELETED

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            returned_state = task.driver.deploy.tear_down(task)
            iscsi_tear_down_mock.assert_called_once_with(mock.ANY, task)
            self.assertEqual(states.DELETED, returned_state)
            self.assertTrue(deallocate_server_hardware_mock.called)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'prepare_cleaning',
                       spec_set=True, autospec=True)
    @mock.patch.object(deploy_utils, 'allocate_server_hardware_to_ironic')
    def test_prepare_cleaning(
            self, allocate_server_hardware_mock, iscsi_prep_clean_mock):
        iscsi_prep_clean_mock.return_value = states.CLEANWAIT
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            ret = task.driver.deploy.prepare_cleaning(task)
            self.assertEqual(states.CLEANWAIT, ret)
            iscsi_prep_clean_mock.assert_called_once_with(mock.ANY, task)
            self.assertTrue(allocate_server_hardware_mock.called)

    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'tear_down_cleaning',
                       spec_set=True, autospec=True)
    @mock.patch.object(deploy_utils, 'deallocate_server_hardware_from_ironic')
    def test_tear_down_cleaning(
            self, deallocate_server_hardware_mock, iscsi_tear_down_clean_mock):
        iscsi_tear_down_clean_mock.return_value = states.CLEANWAIT

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.tear_down_cleaning(task)
            iscsi_tear_down_clean_mock.assert_called_once_with(mock.ANY, task)
            self.assertTrue(deallocate_server_hardware_mock.called)


class OneViewAgentDeployTestCase(test_common.BaseOneViewTest):

    deploy_interface = 'oneview-direct'

    def setUp(self):
        super(OneViewAgentDeployTestCase, self).setUp()
        self.config(manager_url='https://1.2.3.4', group='oneview')
        self.config(username='user', group='oneview')
        self.config(password='password', group='oneview')

        self.port = obj_utils.create_test_port(self.context,
                                               node_id=self.node.id)
        self.info = common.get_oneview_info(self.node)

    def test_get_properties(self):
        expected = common.COMMON_PROPERTIES
        self.assertEqual(expected,
                         deploy.OneViewAgentDeploy().get_properties())

    @mock.patch.object(common, 'validate_oneview_resources_compatibility',
                       spect_set=True, autospec=True)
    @mock.patch.object(agent.AgentDeploy, 'validate',
                       spec_set=True, autospec=True)
    def test_validate(
            self, agent_deploy_validate_mock, mock_validate):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.validate(task)
            self.assertTrue(mock_validate.called)

    @mock.patch.object(agent.AgentDeploy, 'prepare',
                       spec_set=True, autospec=True)
    @mock.patch.object(deploy_utils, 'allocate_server_hardware_to_ironic')
    def test_prepare(
            self, allocate_server_hardware_mock, agent_deploy_prepare_mock):
        self.node.provision_state = states.DEPLOYING
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.prepare(task)
            agent_deploy_prepare_mock.assert_called_once_with(mock.ANY, task)
            self.assertTrue(allocate_server_hardware_mock.called)

    @mock.patch.object(agent.AgentDeploy, 'prepare',
                       spec_set=True, autospec=True)
    def test_prepare_active_node(self, agent_deploy_prepare_mock):
        """Ensure nodes in running states are not inadvertently changed"""
        test_states = list(states.STABLE_STATES)
        test_states.extend([states.CLEANING,
                           states.CLEANWAIT,
                           states.INSPECTING])
        for state in test_states:
            self.node.provision_state = state
            self.node.save()
            agent_deploy_prepare_mock.reset_mock()
            with task_manager.acquire(self.context, self.node.uuid,
                                      shared=False) as task:
                task.driver.deploy.prepare(task)
                agent_deploy_prepare_mock.assert_called_once_with(
                    mock.ANY, task)

    @mock.patch.object(agent.AgentDeploy, 'deploy',
                       spec_set=True, autospec=True)
    def test_deploy(self, agent_deploy_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.deploy(task)
            agent_deploy_mock.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(agent.AgentDeploy, 'tear_down', spec_set=True,
                       autospec=True)
    @mock.patch.object(deploy_utils, 'deallocate_server_hardware_from_ironic')
    def test_tear_down_with_automated_clean_disabled(
            self, deallocate_server_hardware_mock, agent_tear_down_mock):
        CONF.conductor.automated_clean = False
        agent_tear_down_mock.return_value = states.DELETED
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            returned_state = task.driver.deploy.tear_down(task)
            agent_tear_down_mock.assert_called_once_with(mock.ANY, task)
            self.assertEqual(states.DELETED, returned_state)
            self.assertTrue(deallocate_server_hardware_mock.called)

    @mock.patch.object(agent.AgentDeploy, 'prepare_cleaning',
                       spec_set=True, autospec=True)
    @mock.patch.object(deploy_utils, 'allocate_server_hardware_to_ironic')
    def test_prepare_cleaning(
            self, allocate_server_hardware_mock, agent_prep_clean_mock):
        agent_prep_clean_mock.return_value = states.CLEANWAIT
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            ret = task.driver.deploy.prepare_cleaning(task)
            self.assertEqual(states.CLEANWAIT, ret)
            agent_prep_clean_mock.assert_called_once_with(mock.ANY, task)
            self.assertTrue(allocate_server_hardware_mock.called)

    @mock.patch.object(agent.AgentDeploy, 'tear_down_cleaning',
                       spec_set=True, autospec=True)
    @mock.patch.object(deploy_utils, 'deallocate_server_hardware_from_ironic')
    def test_tear_down_cleaning(
            self, deallocate_server_hardware_mock, agent_tear_down_clean_mock):
        agent_tear_down_clean_mock.return_value = states.CLEANWAIT
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.deploy.tear_down_cleaning(task)
            agent_tear_down_clean_mock.assert_called_once_with(mock.ANY, task)
            self.assertTrue(deallocate_server_hardware_mock.called)
