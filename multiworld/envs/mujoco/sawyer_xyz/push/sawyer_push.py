from collections import OrderedDict
import numpy as np
from gym.spaces import Box, Dict

from multiworld.envs.env_util import get_stat_in_paths, \
    create_stats_ordered_dict, get_asset_full_path
from multiworld.core.multitask_env import MultitaskEnv
from multiworld.envs.mujoco.sawyer_xyz.base import SawyerXYZEnv
import mujoco_py
from multiworld.envs.mujoco.cameras import *
#from mujoco_py.mjlib import mjlib

class SawyerPushEnv( SawyerXYZEnv):
    def __init__(
            self,
            obj_low=None,
            obj_high=None,
            tasks = [{'goal': [0, 0.7, 0.02], 'obj_init_pos':[0, 0.6, 0.02]}] , 
            goal_low=None,
            goal_high=None,
            hand_init_pos = (0, 0.4, 0.05),
            rewMode = 'posPlace',
            indicatorDist = 0.05,
            image = False,
            image_dim = 84,
            **kwargs
    ):
        self.quick_init(locals())        
        SawyerXYZEnv.__init__(
            self,
            model_name=self.model_name,
            **kwargs
        )
        if obj_low is None:
            obj_low = self.hand_low

        if goal_low is None:
            goal_low = self.hand_low

        if obj_high is None:
            obj_high = self.hand_high
        
        if goal_high is None:
            goal_high = self.hand_high

        self.objHeight = self.model.body_pos[-1][2]
        assert self.objHeight != 0
        self.max_path_length = 150
        self.image = image
        self.image_dim = image_dim
        
        #import pickle
        #tasks = np.array(pickle.load(open('/home/russell/multiworld/multiworld/envs/goals/PickPlace_20X20.pkl', 'rb'))) 
        #tasks = np.array(pickle.load(open('/home/russell/multiworld/multiworld/envs/goals/pickPlace_20X20_v1.pkl', 'rb')))   
        #tasks = np.array(pickle.load(open('/home/russell/multiworld/multiworld/envs/goals/PickPlace_20X20_simple.pkl', 'rb')))   
        self.tasks = np.array(tasks)
        self.num_tasks = len(tasks)
        self.rewMode = rewMode
        self.Ind = indicatorDist
        self.hand_init_pos = np.array(hand_init_pos)
        self.action_space = Box(
            np.array([-1, -1, -1]),
            np.array([1, 1, 1]),
        )
        self.hand_and_obj_space = Box(
            np.hstack((self.hand_low, obj_low)),
            np.hstack((self.hand_high, obj_high)),
        )
        self.goal_space = Box(goal_low, goal_high)
        #self.initialize_camera(sawyer_pusher_cam)
        
        if self.image:
            self.set_image_obsSpace()

        else:
            self.set_state_obsSpace()

    def set_image_obsSpace(self):
        self.observation_space = Dict([           
                ('img_observation', Box(0, 1, (3*(self.image_dim**2)+self.action_space.shape[0] , ), dtype=np.float32)),  #We append robot config to the image
                ('state_observation', self.hand_and_obj_space), 
            ])
    def set_state_obsSpace(self):
        self.observation_space = Dict([           
                ('state_observation', self.hand_and_obj_space),
                ('state_desired_goal', self.goal_space),
                ('state_achieved_goal', self.goal_space)
            ])

    def get_goal(self):
        return {            
            'state_desired_goal': self._state_goal,
    }
      
    @property
    def model_name(self):
        return get_asset_full_path('sawyer_xyz/sawyer_pick_and_place.xml')

    def step(self, action):

        self.set_xyz_action(action[:3])
        self.do_simulation([0,0])
        self._set_goal_marker(self._state_goal)
        ob = self._get_obs()
        reward , reachDist, placeDist  = self.compute_reward(action, ob)
        self.curr_path_length +=1
        if self.curr_path_length == self.max_path_length:
            done = True
        else:
            done = False
        return ob, reward, done, OrderedDict({ 'reachDist':reachDist,  'placeDist': placeDist, 'epRew': reward})

    def _get_obs(self):
        

        hand = self.get_endeff_pos()
        objPos =  self.get_body_com("obj")
        flat_obs = np.concatenate((hand, objPos))

        if self.image:
            image = self.render(mode = 'nn')
            return dict(img_observation = np.concatenate([image.flatten() , hand]) , 
                        state_observation = flat_obs)

        else:
            return dict(        
                state_observation=flat_obs,
                state_desired_goal=self._state_goal,        
                state_achieved_goal=objPos,
            )

    def render(self, mode = 'human'):

        if mode == 'human':
            im_size = 500 ; norm = 1.0
        else:
            im_size = self.image_dim ; norm = 255.0

        image = self.get_image(width= im_size , height = im_size , camera_name = 'robotview_zoomed').transpose()/norm
        image = image.reshape((3, im_size, im_size))
        image = np.rot90(image, axes = (-2,-1))
        return np.transpose(image , [1,2,0])

   
    def _get_info(self):
        pass

    def _set_goal_marker(self, goal):
        """
        This should be use ONLY for visualization. Use self._state_goal for
        logging, learning, etc.
        """
        self.model.site_pos[self.model.site_name2id('goal')] = (
            goal[:3]
        )
              
    def _set_obj_xyz(self, pos):
        qpos = self.data.qpos.flat.copy()
        qvel = self.data.qvel.flat.copy()
        qpos[9:12] = pos.copy()
        qvel[9:15] = 0
        self.set_state(qpos, qvel)

    def set_obs_manual(self, obs):

        assert len(obs) == 6
        handPos = obs[:3] ; objPos = obs[3:]
        self.data.set_mocap_pos('mocap', handPos)
        self.do_simulation(None)
        self._set_obj_xyz(objPos)
        

    def sample_goals(self, batch_size):
      
        goals = []
        for i in range(batch_size):
           
            task = self.tasks[np.random.randint(0, self.num_tasks)]
            goals.append(task['goal'])

        return { 
            'state_desired_goal': goals,
        }

    def sample_tasks(self, num_tasks):

        indices = np.random.choice(np.arange(self.num_tasks), num_tasks)
        return self.tasks[indices]

    # def adjust_goalPos(self, orig_goal_pos):

    #     return np.array([orig_goal_pos[0], orig_goal_pos[1], self.objHeight])
    # def adjust_initObjPos(self, orig_init_pos):
    #     #This is to account for meshes for the geom and object are not aligned
    #     #If this is not done, the object could be initialized in an extreme position
    #     diff = self.get_body_com('obj')[:2] - self.data.get_geom_xpos('objGeom')[:2]
    #     adjustedPos = orig_init_pos[:2] + diff

    #     #The convention we follow is that body_com[2] is always 0, and geom_pos[2] is the object height
    #     return [adjustedPos[0], adjustedPos[1], 0]

    def change_task(self, task):

        self._state_goal = task['goal']
        self._set_goal_marker(self._state_goal)
        self.obj_init_pos = task['obj_init_pos']
        self.origPlacingDist = np.linalg.norm( self.obj_init_pos[:2] - self._state_goal[:2])

    def reset_arm_and_object(self):

        self._reset_hand()      
        self._set_obj_xyz(self.obj_init_pos)
        self.curr_path_length = 0
        self.pickCompleted = False

    def reset_model(self, reset_arg= None):


        if reset_arg == None:
            task = self.sample_tasks(1)[0]
        else:
            assert type(reset_arg) == int
            task = self.tasks[reset_arg]

        self.change_task(task)
        self.reset_arm_and_object()

        return self._get_obs()

    def _reset_hand(self):

        for _ in range(10):
            self.data.set_mocap_pos('mocap', self.hand_init_pos)
            self.data.set_mocap_quat('mocap', np.array([1, 0, 1, 0]))
            self.do_simulation(None, self.frame_skip)

    def get_site_pos(self, siteName):
        _id = self.model.site_names.index(siteName)
        return self.data.site_xpos[_id].copy()

    def compute_rewards(self, actions, obsBatch):
        #Required by HER-TD3
        assert isinstance(obsBatch, dict) == True
        obsList = obsBatch['state_observation']
        rewards = [self.compute_reward(action, obs)[0] for  action, obs in zip(actions, obsList)]
        return np.array(rewards)

    def compute_reward(self, actions, obs):
           
        state_obs = obs['state_observation']
        endEffPos , objPos = state_obs[0:3], state_obs[3:6] 

        placingGoal = self._state_goal

        rightFinger, leftFinger = self.get_site_pos('rightEndEffector'), self.get_site_pos('leftEndEffector')
        fingerCOM = (rightFinger + leftFinger)/2

        c1 = 1 ; c2 = 1
        reachDist = np.linalg.norm(objPos - fingerCOM)   
        placeDist = np.linalg.norm(objPos[:2] - placingGoal[:2])

        if self.rewMode == 'l2':
            reward = -reachDist - placeDist

        elif self.rewMode == 'l2Sparse':
            reward = - placeDist

        elif self.rewMode == 'l2SparseInd':
            if placeDist < self.Ind:
                reward = - placeDist
            else:
                reward = - self.origPlacingDist


        elif self.rewMode == 'posPlace':
            reward = -reachDist + 100* max(0, self.origPlacingDist - placeDist)

        return [reward, reachDist, min(placeDist, self.origPlacingDist*1.5)] 


     
    def get_diagnostics(self, paths, prefix=''):
        statistics = OrderedDict()       
        return statistics

    def log_diagnostics(self, paths = None, prefix = '', logger = None):

      
        if type(paths[0]) == dict:
            
            for key in paths[0]['env_infos']:
                logger.record_tabular(prefix+ 'sum_'+key, np.mean([sum(path['env_infos'][key]) for path in paths]) )
                logger.record_tabular(prefix+'max_'+key, np.mean([max(path['env_infos'][key]) for path in paths]) )
                logger.record_tabular(prefix+'min_'+key, np.mean([min(path['env_infos'][key]) for path in paths]) )
                logger.record_tabular(prefix + 'last_'+key, np.mean([path['env_infos'][key][-1] for path in paths]) )


        else:
            for i in range(len(paths)):
                prefix=str(i)
                for key in paths[i][0]['env_infos']:
                    logger.record_tabular(prefix+ 'sum_'+key, np.mean([sum(path['env_infos'][key]) for path in paths[i]]) )
                    logger.record_tabular(prefix+'max_'+key, np.mean([max(path['env_infos'][key]) for path in paths[i]]) )
                    logger.record_tabular(prefix+'min_'+key, np.mean([min(path['env_infos'][key]) for path in paths[i]]) )
                    logger.record_tabular(prefix + 'last_'+key, np.mean([path['env_infos'][key][-1] for path in paths[i]]) )
