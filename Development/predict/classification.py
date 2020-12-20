from simpletransformers.classification import ClassificationModel
import torch
import os
import tarfile


class Classification_Transformer():
    base_dir = 'Moti-Me-Application/data'

    def __init__(self, num_labels, load_from_save=False, model_path=None):
        self.load_from_save = load_from_save
        self.model_path = model_path
        self.CUDA = torch.cuda.is_available()
        self.model = self.build_model()

    def build_model(self):
        if self.load_from_save and self.model_path:
            model = ClassificationModel('roberta', self.model_path, use_cuda=self.CUDA, num_labels=num_labels)
        else:
            model = ClassificationModel('roberta', 'roberta-base', use_cuda=self.CUDA, num_labels=num_labels)
        return model

    def predict_ans(self, quote, labels):
        predictions, raw_outputs = self.model.predict(quote)
        return labels[predictions[0]]

    def pack_model(self, model_path='', file_name=''):
        files = [files for root, dirs, files in os.walk(model_path)][0]
        with tarfile.open(file_name+'.tar.gz', 'w:gz') as f:
            for file in files:
                f.add(f'{model_path}/{file}')
        os.rename(f"{os.getcwd()}/{file_name}.tar.gz", f"{model_path}/{file_name}.tar.gz")

    def save(self, zip=False):
        self.model.save_model(f'{Classification_Transformer.base_dir}/outputs', model=self.model.model)
        if zip:
            self.pack_model(f'{Classification_Transformer.base_dir}/outputs', 'roberta-base')

    def unpack_model(model_name=''):
        tar = tarfile.open(f"{model_name}.tar.gz", "r:gz")
        tar.extractall()
        tar.close()


# if __name__ == '__main__':
#     test_quote = "I grew up playing sports. There is a clear line between success and failure."
#     labels = ['thoughtful', 'emotional', 'personal', 'work', 'aspirations']
#     num_labels = len(labels)
#     path = 'Moti-Me-Application/data/outputs'
#     model = Classification_Transformer(
#         num_labels=num_labels, load_from_save=True, model_path=path)
#     ans = model.predict_ans(test_quote, labels)
#     print(ans)
    # model.save(zip=True)
