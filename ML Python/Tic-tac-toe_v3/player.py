import numpy as np
import tensorflow as tf
import random

class Player:

    def __init__(self, action, rnd = False):        
        self.action = action        
        self.count = 0
        self.rnd = rnd
        self.memory = Memory()

        self.gamma = 0.5
        LR = 0.001

        input_size = 9
        h1_size = 30
        h2_size = 60
        h3_size = 30
        output_size = 9
        
        with tf.name_scope('input'):
            self.input = tf.placeholder(tf.float32, [None, input_size], name='input')
            self.target = tf.placeholder(tf.float32, [None, output_size], name='labels')
        
        with tf.name_scope('h1'):
            wh1 = tf.Variable(tf.random_normal([input_size, h1_size], mean=0, stddev=0.01), name='wh1')
            # tf.summary.histogram('wh1', wh1)
            b1 = tf.Variable(tf.zeros([h1_size]), name='bh1')
            # tf.summary.histogram('b1', b1)

            h1 = tf.add(tf.matmul(self.input, wh1), b1, name='linear_transformation')
            h1 = tf.nn.relu(h1, name='relu')

        with tf.name_scope('h2'):
            wh2 = tf.Variable(tf.random_normal([h1_size, h2_size], mean=0, stddev=0.01), name='wh2')
            # tf.summary.histogram('wh2', wh2)
            b2 = tf.Variable(tf.zeros([h2_size]), name='bh2')
            # tf.summary.histogram('b2', b2)

            h2 = tf.add(tf.matmul(h1, wh2), b2, name='linear_transformation')
            h2 = tf.nn.relu(h2, name='relu')

        with tf.name_scope('h3'):
            wh3 = tf.Variable(tf.random_normal([h2_size, h3_size], mean=0, stddev=0.01), name='wh3')
            # tf.summary.histogram('wh3', wh3)
            b3 = tf.Variable(tf.zeros([h3_size]), name='bh3')
            # tf.summary.histogram('b3', b3)

            h3 = tf.add(tf.matmul(h2, wh3), b3, name='linear_transformation')
            h3 = tf.nn.relu(h3, name='relu')

        with tf.name_scope('output'):
            wo = tf.Variable(tf.random_normal([h3_size, output_size], mean=0, stddev=0.01), name='wo')
            # tf.summary.histogram('wo', wo)
            bo = tf.Variable(tf.zeros([output_size]), name='bo')
            # tf.summary.histogram('bo', bo)
            
            self.output = tf.add(tf.matmul(h3, wo), bo, name='linear_transformation')
            self.output = tf.nn.sigmoid(self.output, name='sigmoid')
            tf.summary.scalar('output', self.output)

        with tf.name_scope('cost'):      
            # MSE      
            error = tf.reduce_sum(tf.pow(tf.subtract(self.output, self.target), 2))
            self.loss = tf.reduce_mean(error)
            # tf.summary.scalar('cost', self.loss)

            # CATEGORICAL CROSSENTROPY
            # self.loss = tf.reduce_mean(tf.negative(tf.reduce_sum(tf.multiply(self.target, tf.log(self.output)))))

        with tf.name_scope('optimizer'):
            self.optimizer = tf.train.AdamOptimizer(learning_rate=LR).minimize(self.loss)

        #self.sess = tf.Session(config=tf.ConfigProto(log_device_placement=True))
        self.sess = tf.Session()        
        self.sess.run(tf.global_variables_initializer())        

        self.merged = tf.summary.merge_all()
        self.writter = tf.summary.FileWriter('C:/tmp/logs/train', self.sess.graph)        
        
        # # para salvar o modelo treinado
        # saver = tf.train.Saver()
                    
        # print(input)
        # print(scores)

    def play(self, s):                    
        actions = self.sess.run([ self.output ], feed_dict={ self.input: np.array([s]) })

        return actions

    def learn(self):
        if self.rnd:
            return

        games = self.memory.read()        

        input = []
        target = []

        for game in games:
            events = game[1]

            # THE LAST ACTION IS CORRECTED WITH HIS S_ VALUE (USUAL Q-LEARNING)
            # THE ACTION-1 AND ON USE THE NEW VALUE FROM LAST ACTION * GAMMA AS TARGET 
            last_event = events[-1]

            output_s = self.play(last_event.s)
            output_s_ = self.play(last_event.s_)
            event_output_s_ = np.argmax(output_s_)
            cumulative_r = self.gamma * output_s_[0][0][event_output_s_] + last_event.r
            output_s[0][0][last_event.a] = cumulative_r

            input.append(last_event.s)        
            target.append(output_s[0][0])

            for event in reversed(events[:-1]):            
                cumulative_r = cumulative_r * self.gamma  + event.r

                output_s = self.play(event.s)
                output_s[0][0][event.a] = cumulative_r

                input.append(event.s)
                target.append(output_s[0][0])
                        
        summary, _, _ = self.sess.run([ self.merged, self.input, self.optimizer ], feed_dict={ self.input: np.asarray(input).astype(float), self.target: np.asarray(target) })    
        self.writter.add_summary(summary)            

        # self.memory.reset()

    def observe(self, game, s, a, r, s_, done):
        self.memory.add(game, s, a, r, s_, done)
    
class Memory:            
    def __init__(self, capacity = 1000):
        self.games = {}
        self.capacity = capacity

    def add(self, game, s, a, r, s_, done):             
        if len(self.games) == self.capacity:
            for key in self.games:
                del self.games[key]                
                break

        event = Event(s, a, r, s_, done)

        if game not in self.games:
            self.games[game] = []

        self.games[game].append(event)

    def read(self, n = 10):      
        qtd = len(self.games) if n > len(self.games) else n        
        sample = random.sample(self.games.items(), qtd)

        return sample

    def reset(self):
        self.games = {}

class Event:
    def __init__(self, s, a, r, s_, done):
        self.s = s
        self.a = a
        self.r = r
        self.s_ = s_
        self.done = done

class Game:
    def __init__(self):
        self.events = []

    def add(self, event):
        self.events.append(event)    