import numpy as np

def read_train_dataset():
    with open('dataset/train-images.idx3-ubyte', 'rb') as f:
        id = int.from_bytes(f.read(4), byteorder="big", signed=False)
        num_images = int.from_bytes(f.read(4), byteorder="big", signed=False)
        num_rows = int.from_bytes(f.read(4), byteorder="big", signed=False)
        num_cols = int.from_bytes(f.read(4), byteorder="big", signed=False)
        image_size = num_rows * num_cols
        images = np.empty((num_images, num_rows, num_cols), dtype=np.uint8)
        for i in range(0, num_images):
            current_image = f.read(image_size)
            if len(current_image) < image_size:
                raise ValueError(f"Missing image, expect {num_images} images but receive {i} images")
            current_image = np.frombuffer(current_image, dtype=np.uint8).reshape(num_rows, num_cols)
            images[i] = current_image
    return images

def read_label_dataset():
    with open('dataset/train-labels.idx1-ubyte', 'rb') as f:
        id = int.from_bytes(f.read(4), byteorder="big", signed=False)
        num_labels = int.from_bytes(f.read(4), byteorder="big", signed=False)
        labels = [int.from_bytes(f.read(1), byteorder="big", signed=False) for i in range(0, num_labels)]
    return labels

if __name__ == '__main__':
    images = read_train_dataset()
    # for i in range(0, 28):
    #     for j in range(0, 28):
    #         print(images[0, i, j], end='  ')
    #     print()
    labels = read_label_dataset()
    print(labels[:100])