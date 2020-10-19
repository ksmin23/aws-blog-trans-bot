# AWS Blog Post Translation Bot

영문 [AWS의 최신 블로그 포스팅](https://aws.amazon.com/ko/blogs/aws/)을 한국어로 기계 번역해서 한국어 번역 내용(아래 그림 참조)을 email로 전송해주는 프로젝트.<br/>

  **Figure 1.** 영문 AWS의 최신 블로그 포스팅을 한국어로 번역한 결과

  ![sample-blog-post-translated](./assets/sample-blog-post-translated.png)

## Architecture
 ![aws-blog-trans-bot-arch](./assets/aws-blog-trans-bot-arch.svg)

## Deployment

1. [Getting Started With the AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)를 참고해서 cdk를 설치하고,
cdk를 실행할 때 사용할 IAM User를 생성한 후, `~/.aws/config`에 등록한다.
예를 들어서, `cdk_user`라는 IAM User를 생성 한 후, 아래와 같이 `~/.aws/config`에 추가로 등록한다.

    ```shell script
    $ cat ~/.aws/config
    [profile cdk_user]
    aws_access_key_id=AKIAIOSFODNN7EXAMPLE
    aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    region=us-east-1
    ```

2. Lambda Layer에 등록할 Python 패키지를 저장할 s3 bucket을 생성한다. 예를 들어, `lambda-layer-resources` 라는 이름의 s3 bucket을 생성한다.

   ```shell script
    $ aws s3api create-bucket --bucket lambda-layer-resources --region us-east-1
    ```

3. 아래와 같이 소스 코드를 git clone 한 후에, `build-aws-lambda-layer.sh` 를 이용해서
Lambda Layer에 등록할 Python 패키지를 생성해서 s3에 저장한다.

    ```shell script
    $ git clone https://github.com/ksmin23/aws-rss-feed-trans-bot.git
    $ cd aws-rss-feed-trans-bot
    $ python3 --version
    Python 3.6.9
    $ python3 -m venv .env
    $ source .env/bin/activate
    (.env) $ pip install -r requirements.txt
    (.env) $ ./build-aws-lambda-layer.sh lambda-layer-resources/var
    ```

    :warning: **Python 3.7**을 사용하는 경우, `./aws_blog_trans_bot/aws_blog_trans_bot_stack.py` 파일에서 `_lambda.Runtime.PYTHON_3_6` 를 `_lambda.Runtime.PYTHON_3_7` 로 변경해서, AWS Lambda Function과 Lambda Layer에서 동일한 Runtime 버전(**Python 3.7**)을 사용하도록 해야한다.<br/>
    Lambda Function과 Lambda Layer의 Python Runtime 버전이 동일하지 않을 경우, `BlogTransBot` 람다 함수 실행 될 때 다음과 같은 에러가 발생한다.</br>
    ![blog-trans-bot-lambda-fn-error](./asset/../assets/blog-trans-bot-lambda-fn-error.png)


4. `cdk.context.json` 파일을 열어서, `lib_bucket_name`에 Lambda Layer에 등록할 Python 패키지가 저장된 s3 bucket 이름을 적고,<br/>`email_from_address`과 `email_to_addresses`에 e-mail 발신자와 수신자들 목록을 각각 넣는다.<br/> RSS Feed를 읽는 주기를 변경하고자 하는 경우, `event_schedule`을 crontab 문법 처럼 등록 한다.<br/>
`event_schedule` 기본 값은 매 시간 마다 RSS Feed를 읽어서 번역한다.

    ```json
    {
      "lib_bucket_name": "Your-S3-Bucket-Name-Of-Lambda-Layer-Lib",
      "email_from_address": "Your-Sender-Email-Addr",
      "email_to_addresses": "Your-Receiver-Email-Addr-List",
      "dry_run": "false",
      "trans_dest_lang": "ko",
      "event_schedule": "0 * * * *",
      "blog_base_url": "https://aws.amazon.com/blogs",
      "blog_categories": "aws"
    }
    ```
    - `email_from_address`은 [Amazon SES에서 이메일 주소 확인](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-email-addresses.html)를 참고해서 반드시 사용 가능한 email 주소인지 확인한다. (배포 전에 한번만 확인 하면 된다.)
    예를 들어, `sender@amazon.com`라는 email 주소를 확인하려면 다음과 같이 한다.
      ```
      aws ses verify-email-identity --email-address sender@amazon.com
      ```
    - AWS Blog 중 다른 카테고리의 블로그 포스트를 번역하고 싶은 경우, `blog_categories`에 [category code](#aws-blog-category-codes)를 쉼표(`,`)로 구분해서 넣으면 된다. 예를 들어, AWS News Blog, AWS Big Data Blog, AWS Machine Learning Blog의 블로그 포스트를 번역하고 싶은 경우, "aws,big-data,machine-learning"을 `blog_categories`에 넣는다.
      ```
      {"blog_categories": "aws,big-data,machine-learning"}
      ```

5. `cdk deploy` 명령어를 이용해서 배포한다.
    ```shell script
    (.env) $ cdk --profile=cdk_user deploy
    ```

6. 배포한 애플리케이션을 삭제하려면, `cdk destroy` 명령어를 아래와 같이 실행 한다.
    ```shell script
    (.env) $ cdk --profile=cdk_user destroy
    ```

### Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

## Test

1. AWS 웹 콘솔에서 Lambda 서비스를 선택한 후, `BlogRssReader` 람다 함수를 선택 한다.
![lambda-function-list](./assets/lambda-function-list.png)

2. **Configure test events**를 선택한다.
![lambda-configure-test-events](./assets/lambda-configure-test-events.png)

3. **Cloud Watch Scheduled Event**를 생성후 저장한다.<br/>
(이 예제에서는 `TestScheduledEvent` 라는 이름을 사용한다.)
![lambda-test-scheduled-event](./assets/lambda-test-scheduled-event.png)

4. **Test** 버튼을 클릭해서 람다 함수를 실행한다.
![lambda-run-test](./assets/lambda-run-test.png)

## <a name="aws-blog-category-codes"></a>AWS Blog Links
| Category | Link | Category Code |
|:------:|:---|:------:|
| Architecture | https://aws.amazon.com/blogs/architecture/ | architecture |
| AWS Cost Management | https://aws.amazon.com/blogs/aws-cost-management/ | aws-cost-management |
| AWS Partner Network | https://aws.amazon.com/blogs/apn/ | apn |
| AWS Marketplace | https://aws.amazon.com/blogs/awsmarketplace/ | awsmarketplace |
| AWS News | https://aws.amazon.com/blogs/aws/ | aws |
| Big Data | https://aws.amazon.com/blogs/big-data/ | big-data |
| Business Productivity | https://aws.amazon.com/blogs/business-productivity/ | business-productivity |
| Compute | https://aws.amazon.com/blogs/compute/ | compute |
| Contact Center | https://aws.amazon.com/blogs/contact-center/ | contact-center |
| Containers | https://aws.amazon.com/blogs/containers/ | containers |
| Database | https://aws.amazon.com/blogs/database/ | database |
| Desktop & Application Streaming | https://aws.amazon.com/blogs/desktop-and-application-streaming/ | desktop-and-application-streaming |
| Developer | https://aws.amazon.com/blogs/developer/ | developer |
| DevOps | https://aws.amazon.com/blogs/devops/ | devops |
| Enterprise Strategy | https://aws.amazon.com/blogs/enterprise-strategy/ | enterprise-strategy |
| Front-End Web & Mobile | https://aws.amazon.com/blogs/mobile/ | mobile |
| Game Tech | https://aws.amazon.com/blogs/gametech/ | gametech |
| Infrastructure & Automation | https://aws.amazon.com/blogs/infrastructure-and-automation/ | infrastructure-and-automation |
| Industries | https://aws.amazon.com/blogs/industries/ | industries |
| Internet of Things | https://aws.amazon.com/blogs/iot/ | iot |
| Machine Learning | https://aws.amazon.com/blogs/machine-learning/ | machine-learning |
| Management & Governance | https://aws.amazon.com/blogs/mt/ | mt |
| Media | https://aws.amazon.com/blogs/media/ | media |
| Messaging & Targeting | https://aws.amazon.com/blogs/messaging-and-targeting/ | messaging-and-targeting |
| Modernizing with AWS | https://aws.amazon.com/blogs/modernizing-with-aws/ | modernizing-with-aws |
| Networking & Content Delivery | https://aws.amazon.com/blogs/networking-and-content-delivery/ | networking-and-content-delivery |
| Open Source | https://aws.amazon.com/blogs/opensource/ | opensource |
| Public Sector | https://aws.amazon.com/blogs/publicsector/ | publicsector |
| Robotics | https://aws.amazon.com/blogs/robotics/ | robotics |
| SAP | https://aws.amazon.com/blogs/awsforsap/ | awsforsap |
| Security, Identity, & Compliance | https://aws.amazon.com/blogs/security/ | security |
| Startups | https://aws.amazon.com/blogs/startups/ | startups |
| Storage | https://aws.amazon.com/blogs/storage/ | storage |
| Training & Certification | https://aws.amazon.com/blogs/training-and-certification/ | training-and-certification |
