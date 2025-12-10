<?php
// uploadFile.php
if (isset($_POST['submit'])) {
    $file = $_FILES['file'];
    
    $fileName = $_FILES['file']['name'];
    $fileTmpName = $_FILES['file']['tmp_name'];
    $fileSize = $_FILES['file']['size'];
    $fileError = $_FILES['file']['error'];
    $fileType = $_FILES['file']['type'];

    $fileExt = explode('.', $fileName); //Separates file name with the extension
    $fileActualExt = strtolower(end($fileExt)); //Gets the extension and makes it lowercase

    $allowed = array('jpg', 'jpeg', 'png', 'pdf', 'docx', 'pptx'); //Allowed file types
    if (in_array($fileActualExt, $allowed)) {
        if ($fileError === 0) {
            if ($fileSize < 5000000) { //Limit file size to 5MB
                $fileNameNew = uniqid('', true).".".$fileActualExt; //Creates a unique name for the file
                $fileDestination = 'uploads/'.$fileNameNew; //Destination folder
                move_uploaded_file($fileTmpName, $fileDestination); //Moves the file to the destination
                echo "<div class='alert alert-success' role='alert'>
                        File uploaded successfully! <a href='viewFile.php?file=".$fileNameNew."' class='alert-link'>View File here!</a>.
                    </div>";
            } else {
                echo "Your file is too big!";
            }
        } else {
            echo "There was an error uploading your file!";
        }
    } else {
        echo "You cannot upload files of this type!";
    }
//     $targetDir = "uploads/";
//     $targetFile = $targetDir . basename($_FILES["fileUpload"]["name"]);
//     $uploadOk = 1;
//     $fileType = strtolower(pathinfo($targetFile, PATHINFO_EXTENSION));

//     // Check if file already exists
//     if (file_exists($targetFile)) {
//         echo "Sorry, file already exists.";
//         $uploadOk = 0;
//     }

//     // Check file size (limit to 5MB)
//     if ($_FILES["fileUpload"]["size"] > 5000000) {
//         echo "Sorry, your file is too large.";
//         $uploadOk = 0;
//     }

//     // Allow certain file formats
//     $allowedTypes = array("jpg", "png", "jpeg", "gif", "pdf", "docx");
//     if (!in_array($fileType, $allowedTypes)) {
//         echo "Sorry, only JPG, JPEG, PNG, GIF, PDF & DOCX files are allowed.";
//         $uploadOk = 0;
//     }

//     // Check if $uploadOk is set to 0 by an error
//     if ($uploadOk == 0) {
//         echo "Sorry, your file was not uploaded.";
//     } else {
//         if (move_uploaded_file($_FILES["fileUpload"]["tmp_name"], $targetFile)) {
//             echo "The file ". htmlspecialchars(basename($_FILES["fileUpload"]["name"])). " has been uploaded.";
//         } else {
//             echo "Sorry, there was an error uploading your file.";
//         }
//     }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document</title>
</head>
<body>
    <form action="uploadFile.php" method="post" enctype="multipart/form-data">
        <label for="fileUpload">Choose a file to upload:</label>
        <input type="file" name="file" id="file" required>
        <br><br>
        <button type="submit" value="Upload File" name="submit">Upload File</button>
    </form>
</body>
</html>