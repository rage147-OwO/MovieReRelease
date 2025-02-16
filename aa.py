if __name__ == "__main__":
    temp = input().split(" ")
    appleLen = int(temp[0])
    quizLen = int(temp[1])
    taste = list(map(int, input().split()))  # 사과맛리스트
    sizes = list(map(int, input().split()))  # 사과크기리스트
    notExist = True
    answer = []
    for i in range(quizLen):
        p = int(input())
        notExist = True
        count = 0
        _maxSize = 0
        for j in range(appleLen):
            if taste[j] >= p:
                notExist = False
                if sizes[j] >= _maxSize:
                    _maxSize = sizes[j]

        for j in range(appleLen):
            if taste[j] >= p:
                if sizes[j] == _maxSize:
                    count += 1  

        if notExist:
            answer.append(0)
        else:
            answer.append(count)
    for i in range(len((answer))):
        print(answer[i])
