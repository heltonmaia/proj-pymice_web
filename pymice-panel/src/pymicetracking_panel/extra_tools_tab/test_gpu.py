import torch
from ultralytics import YOLO

def check_gpu_support() -> bool:
    print("="*50)
    print("Verificando suporte a GPU para YOLO")
    print("="*50)
    
    # 1. Verificando se o PyTorch reconhece a GPU
    print("\n[1] Informações básicas da GPU:")
    if torch.cuda.is_available():
        print(f"✅ GPU detectada: {torch.cuda.get_device_name(0)}")
        print(f"🚀 Versão do CUDA: {torch.version.cuda}")
    else:
        print("❌ Nenhuma GPU detectada pelo PyTorch")
        return False
    
    # 2. Testando alocação de memória
    print("\n[2] Teste de alocação de memória:")
    try:
        x = torch.randn(3, 3).cuda()
        print("✅ Memória GPU alocada com sucesso")
        del x
    except Exception as e:
        print(f"❌ Falha ao alocar memória GPU: {str(e)}")
        return False
    
    # 3. Testando um modelo YOLO pequeno
    print("\n[3] Testando modelo YOLO (pode demorar um pouco)...")
    try:
        model = YOLO('yolov8n.pt')  # Modelo nano (o menor)
        model.to('cuda')
        results = model('https://ultralytics.com/images/bus.jpg', verbose=False)
        print("✅ YOLO executado com sucesso na GPU")
        print(f"📊 Objetos detectados: {len(results[0].boxes)}")
        return True
    except Exception as e:
        print(f"❌ Falha ao executar YOLO na GPU: {str(e)}")
        return False

if __name__ == "__main__":
    if check_gpu_support():
        print("\n🎉 Sua GPU está pronta para uso com YOLO!")
    else:
        print("\n⚠️  Sua GPU não pode ser usada com YOLO ou há problemas de configuração.")
        print("Recomendações:")
        print("1. Verifique se você tem drivers NVIDIA atualizados")
        print("2. Instale o PyTorch com suporte a CUDA: https://pytorch.org/get-started/locally/")
        print("3. Se estiver usando notebook/cloud, ative o suporte a GPU")