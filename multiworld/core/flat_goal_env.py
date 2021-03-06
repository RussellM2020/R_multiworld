from gym.spaces import  Dict

from gym.spaces import Box 


import numpy as np

from multiworld.core.wrapper_env import ProxyEnv


class FlatGoalEnv(ProxyEnv):
    def __init__(self, wrapped_env, obs_keys=None, goal_keys=[]):
        self.quick_init(locals())
        super(FlatGoalEnv, self).__init__(wrapped_env)

        if obs_keys is None:
            obs_keys = ['observation']
        # if goal_keys is None:
        #     goal_keys = ['desired_goal']
        for k in obs_keys:
            
            assert k in self.wrapped_env.observation_space.spaces


        for k in goal_keys:
            assert k in self.wrapped_env.observation_space.spaces
        assert isinstance(self.wrapped_env.observation_space, Dict)

        self.obs_keys = obs_keys
        self.goal_keys = goal_keys
        # TODO: handle nested dict


        self.observation_space = Box(
            np.hstack([
                self.wrapped_env.observation_space.spaces[k].low
                for k in obs_keys
            ]),
            np.hstack([
                self.wrapped_env.observation_space.spaces[k].high
                for k in obs_keys
            ]),
            dtype = np.float32
        )

        if len(goal_keys)>0:
            self.goal_space = Box(
                np.hstack([
                    self.wrapped_env.observation_space.spaces[k].low
                    for k in goal_keys
                ]),
                np.hstack([
                    self.wrapped_env.observation_space.spaces[k].high
                    for k in goal_keys
                ]),
                dtype = np.float32
            )
        self._goal = None

    def step(self, action):
        obs, reward, done, info = self.wrapped_env.step(action)
        flat_obs = np.hstack([obs[k] for k in self.obs_keys])
        return flat_obs, reward, done, info

    def reset(self, reset_args = None):
        obs = self.wrapped_env.reset(reset_args)
        if len(self.goal_keys)>0:
            self._goal = np.hstack([obs[k] for k in self.goal_keys])
        return np.hstack([obs[k] for k in self.obs_keys])


    def get_flat_obs(self):
        obs = self.wrapped_env._get_obs()

        return np.hstack([obs[k] for k in self.obs_keys])


        




    def get_goal(self):
        return self._goal
