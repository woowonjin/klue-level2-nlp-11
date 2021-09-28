import pickle as pickle
import os
import pandas as pd
import torch
import sklearn
import numpy as np
from sklearn.metrics import accuracy_score, recall_score, precision_score, f1_score
from transformers import AutoTokenizer, AutoConfig, AutoModelForSequenceClassification, Trainer, TrainingArguments, RobertaConfig, RobertaTokenizer, RobertaForSequenceClassification, BertTokenizer
from load_data import *

import argparse

def klue_re_micro_f1(preds, labels):
    """KLUE-RE micro f1 (except no_relation)"""
    label_list = ['no_relation', 'org:top_members/employees', 'org:members',
       'org:product', 'per:title', 'org:alternate_names',
       'per:employee_of', 'org:place_of_headquarters', 'per:product',
       'org:number_of_employees/members', 'per:children',
       'per:place_of_residence', 'per:alternate_names',
       'per:other_family', 'per:colleagues', 'per:origin', 'per:siblings',
       'per:spouse', 'org:founded', 'org:political/religious_affiliation',
       'org:member_of', 'per:parents', 'org:dissolved',
       'per:schools_attended', 'per:date_of_death', 'per:date_of_birth',
       'per:place_of_birth', 'per:place_of_death', 'org:founded_by',
       'per:religion']
    no_relation_label_idx = label_list.index("no_relation")
    label_indices = list(range(len(label_list)))
    label_indices.remove(no_relation_label_idx)
    return sklearn.metrics.f1_score(labels, preds, average="micro", labels=label_indices) * 100.0

def klue_re_auprc(probs, labels):
    """KLUE-RE AUPRC (with no_relation)"""
    labels = np.eye(30)[labels]

    score = np.zeros((30,))
    for c in range(30):
        targets_c = labels.take([c], axis=1).ravel()
        preds_c = probs.take([c], axis=1).ravel()
        precision, recall, _ = sklearn.metrics.precision_recall_curve(targets_c, preds_c)
        score[c] = sklearn.metrics.auc(recall, precision)
    return np.average(score) * 100.0

def compute_metrics(pred):
  """ validation을 위한 metrics function """
  labels = pred.label_ids
  preds = pred.predictions.argmax(-1)
  probs = pred.predictions

  # calculate accuracy using sklearn's function
  f1 = klue_re_micro_f1(preds, labels)
  auprc = klue_re_auprc(probs, labels)
  acc = accuracy_score(labels, preds) # 리더보드 평가에는 포함되지 않습니다.

  return {
      'micro f1 score': f1,
      'auprc' : auprc,
      'accuracy': acc,
  }

def label_to_num(label, dict_pkl):
  num_label = []
  with open(dict_pkl, 'rb') as f:
    dict_label_to_num = pickle.load(f)
  for v in label:
    num_label.append(dict_label_to_num[v])
  
  return num_label

def train(args):
  # load model and tokenizer
  # MODEL_NAME = "bert-base-uncased"
  MODEL_NAME = args.model_name

  tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

  # load dataset
  train_dataset = load_data(args.train_csv_path)
  # dev_dataset = load_data("../dataset/train/dev.csv") # validation용 데이터는 따로 만드셔야 합니다.

  train_label = label_to_num(train_dataset['label'].values, args.label_to_num)
  # dev_label = label_to_num(dev_dataset['label'].values)

  # tokenizing dataset
  tokenized_train = tokenized_dataset(train_dataset, tokenizer)
  # tokenized_dev = tokenized_dataset(dev_dataset, tokenizer)

  # make dataset for pytorch.
  RE_train_dataset = RE_Dataset(tokenized_train, train_label)
  # RE_dev_dataset = RE_Dataset(tokenized_dev, dev_label)

  device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

  print(device)
  # setting model hyperparameter
  model_config =  AutoConfig.from_pretrained(MODEL_NAME)
  model_config.num_labels = args.num_labels

  model =  AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, config=model_config)
  print(model.config)
  model.parameters
  model.to(device)
  
  # 사용한 option 외에도 다양한 option들이 있습니다.
  # https://huggingface.co/transformers/main_classes/trainer.html#trainingarguments 참고해주세요.
  training_args = TrainingArguments(
    output_dir=args.output_dir,
    save_total_limit=args.save_limit,
    save_steps=args.save_steps,
    num_train_epochs=args.num_train_epochs,
    learning_rate=args.learning_rate,
    per_device_train_batch_size=args.train_batch_size,
    per_device_eval_batch_size=args.eval_batch_size,
    warmup_steps=args.warmup_steps,
    weight_decay=args.weight_decay,
    logging_dir=args.logging_dir,
    logging_steps=args.logging_steps,
    evaluation_strategy=args.evaluation_strategy,
    eval_steps = args.eval_steps,
    load_best_model_at_end = True 
  )
  trainer = Trainer(
    model=model,                         # the instantiated 🤗 Transformers model to be trained
    args=training_args,                  # training arguments, defined above
    train_dataset=RE_train_dataset,         # training dataset
    eval_dataset=RE_train_dataset,             # evaluation dataset
    compute_metrics=compute_metrics         # define metrics function
  )

  # train model
  trainer.train()
  model.save_pretrained('./best_model')


if __name__ == '__main__':
  parser = argparse.ArgumentParser()

  
  parser.add_argument('--model_name', type=str, default='klue/bert-base', help='model name')
  parser.add_argument('--train_csv_path', type=str, default='../dataset/train/train.csv', help='train data csv path')
  parser.add_argument('--label_to_num', type=str, default='dict_label_to_num.pkl', help='dictionary information of label to number')
  parser.add_argument('--num_to_label', type=str, default='dict_num_to_label.pkl', help='dictionary information of number to label')
  parser.add_argument('--num_labels', type=int, default=30, help='number of labels')
  parser.add_argument('--output_dir', type=str, default='./results', help='output directory')
  parser.add_argument('--save_limit', type=int, default=5, help='number of total save model')
  parser.add_argument('--save_steps', type=int, default=500, help='model saving step')
  parser.add_argument('--num_train_epochs', type=int, default=20, help='total number of training epochs')
  parser.add_argument('--learning_rate', type=float, default=5e-5, help='learning rate')
  parser.add_argument('--train_batch_size', type=int, default=16, help='batch size per device during training')
  parser.add_argument('--eval_batch_size', type=int, default=16, help='batch size for evaluation')
  parser.add_argument('--warmup_steps', type=int, default=500, help='number of warmup steps for learning rate scheduler')
  parser.add_argument('--weight_decay', type=float, default=0.01, help='strength of weight decay')
  parser.add_argument('--logging_dir', type=str, default='./logs', help='directory for storing logs')
  parser.add_argument('--logging_steps', type=int, default=100, help='log saving step')
  parser.add_argument('--evaluation_strategy', type=str, default='steps', help='evaluation strategy to adopt during training')

  parser.add_argument('--eval_steps', type=int, default=500, help='evaluation step')
  args = parser.parse_args()

  train(args)